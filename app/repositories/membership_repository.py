"""Statements against ``memberships``, plus the permission resolution.

Reads filter ``deleted_at IS NULL`` explicitly rather than relying on a database
default or a session-level filter. The predicate is visible at each call site,
which is worth the repetition: a soft-delete filter that is invisible is the kind of
thing that ships a deleted row to a user.

``effective_permissions`` lives here rather than in a module of its own because the
membership is what it resolves: one query joins the user, the role, and that role's
permission keys through one membership row.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Row, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.identity.rbac import SYS_ADMIN_ROLE_KEY
from app.models.identity import (
    Membership,
    Permission,
    Role,
    RolePermission,
    Shop,
    User,
)
from app.repositories import role_repository, user_repository


async def create_membership(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    shop_id: uuid.UUID | None,
    role_id: uuid.UUID,
) -> Membership:
    membership = Membership(user_id=user_id, shop_id=shop_id, role_id=role_id)
    session.add(membership)
    await session.flush()
    return membership


async def list_memberships(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Shop, Role]]:
    """Every live shop this user belongs to, oldest first.

    Oldest first matters: it makes "the active shop" deterministic on login without
    the user having to choose on their first visit.
    """

    statement = (
        select(Shop, Role)
        .join(Membership, Membership.shop_id == Shop.id)
        .join(Role, Role.id == Membership.role_id)
        .where(
            Membership.user_id == user_id,
            Membership.deleted_at.is_(None),
            Shop.deleted_at.is_(None),
            Role.deleted_at.is_(None),
        )
        .order_by(Membership.created_at, Shop.name)
    )
    return [(row[0], row[1]) for row in (await session.execute(statement)).all()]


async def find_membership(
    session: AsyncSession, *, user_id: uuid.UUID, shop_id: uuid.UUID
) -> tuple[Shop, Role] | None:
    statement = (
        select(Shop, Role)
        .join(Membership, Membership.shop_id == Shop.id)
        .join(Role, Role.id == Membership.role_id)
        .where(
            Membership.user_id == user_id,
            Membership.shop_id == shop_id,
            Membership.deleted_at.is_(None),
            Shop.deleted_at.is_(None),
            Role.deleted_at.is_(None),
        )
    )
    row: Row[tuple[Shop, Role]] | None = (await session.execute(statement)).first()
    return (row[0], row[1]) if row is not None else None


async def set_membership_role(
    session: AsyncSession, *, user_id: uuid.UUID, shop_id: uuid.UUID, role_id: uuid.UUID
) -> None:
    await session.execute(
        update(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.shop_id == shop_id,
            Membership.deleted_at.is_(None),
        )
        .values(role_id=role_id)
    )


async def set_membership_role_by_key(
    session: AsyncSession, *, user_email: str, shop_id: uuid.UUID, role_key: str
) -> None:
    """A convenience for tests and operator scripts.

    Kept in the repository rather than in the test, so tests do not hand-write SQL
    and cannot drift from the schema.
    """

    user = await user_repository.find_user_by_email(session, user_email)
    role = await role_repository.get_role_by_key(session, role_key)
    if user is None or role is None:
        raise LookupError(f"no user {user_email!r} or role {role_key!r}")
    await set_membership_role(
        session, user_id=user.id, shop_id=shop_id, role_id=role.id
    )


async def soft_delete_memberships_for_shop(
    session: AsyncSession, shop_id: uuid.UUID
) -> None:
    await session.execute(
        update(Membership)
        .where(Membership.shop_id == shop_id, Membership.deleted_at.is_(None))
        .values(deleted_at=datetime.now(UTC))
    )


async def soft_delete_platform_membership(
    session: AsyncSession, user_id: uuid.UUID
) -> None:
    """Retire a user's platform role, keeping the row.

    Demotion is an operator action rather than a request path, but the refresh flow
    has to survive it: a session whose platform membership is gone must lose admin
    authority, and this is how that state is created.
    """

    await session.execute(
        update(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.shop_id.is_(None),
            Membership.deleted_at.is_(None),
        )
        .values(deleted_at=datetime.now(UTC))
    )


async def upsert_platform_membership(
    session: AsyncSession, *, user_id: uuid.UUID, role_id: uuid.UUID
) -> None:
    """Point the user's live platform membership at ``role_id``, inserting it if absent.

    One platform membership per user is a database rule (the partial unique index
    ``memberships_user_platform_live``), so a promotion updates that row rather than
    adding a second one: an insert would be an ``IntegrityError`` instead of the
    promotion the operator asked for.
    """

    updated = await session.execute(
        update(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.shop_id.is_(None),
            Membership.deleted_at.is_(None),
        )
        .values(role_id=role_id)
        .returning(Membership.id)
    )
    if updated.first() is None:
        await create_membership(session, user_id=user_id, shop_id=None, role_id=role_id)


async def effective_permissions(
    session: AsyncSession, *, user_id: uuid.UUID, shop_id: uuid.UUID
) -> tuple[User, Role, list[str]] | None:
    """Resolve the live user, their role, and that role's permission keys.

    One query over four small indexed tables. Returns ``None`` when the user has no
    live membership in that shop, which the caller turns into an authentication
    failure rather than an empty permission set: "you do not belong here" and "you
    may do nothing here" are different answers.

    Every join carries its own soft-delete predicate. A membership to a deleted shop,
    or a membership holding a deleted role, is not a membership.
    """

    statement = (
        select(User, Role, Permission.key)
        .join(
            Membership,
            (Membership.user_id == User.id) & (Membership.shop_id == shop_id),
        )
        .join(Role, Role.id == Membership.role_id)
        .join(Shop, Shop.id == Membership.shop_id)
        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
        .outerjoin(Permission, Permission.id == RolePermission.permission_id)
        .where(
            User.id == user_id,
            User.deleted_at.is_(None),
            User.deactivated_at.is_(None),
            Membership.deleted_at.is_(None),
            Role.deleted_at.is_(None),
            Shop.deleted_at.is_(None),
        )
    )
    rows = (await session.execute(statement)).all()
    if not rows:
        return None
    user, role = rows[0][0], rows[0][1]
    keys = sorted({row[2] for row in rows if row[2] is not None})
    return user, role, keys


async def find_platform_membership(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[Role, list[str]] | None:
    """The user's ``sys_admin`` platform role and its permissions, or None.

    Filtered on the role key, not merely on ``shop_id IS NULL``: a platform
    membership that grants some other role is not platform oversight, and the caller
    (admin login, refresh, principal resolution) treats a found row as authority.
    """

    statement = (
        select(Role, Permission.key)
        # Membership is named as the starting point because Role and Permission are
        # both in the select list, and only an explicit left side tells the compiler
        # which table the platform-role join hangs off.
        .select_from(Membership)
        .join(Role, Role.id == Membership.role_id)
        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
        .outerjoin(Permission, Permission.id == RolePermission.permission_id)
        .where(
            Membership.user_id == user_id,
            Membership.shop_id.is_(None),
            Membership.deleted_at.is_(None),
            Role.deleted_at.is_(None),
            Role.key == SYS_ADMIN_ROLE_KEY,
        )
    )
    rows = (await session.execute(statement)).all()
    if not rows:
        return None
    role = rows[0][0]
    permissions = sorted({row[1] for row in rows if row[1] is not None})
    return role, permissions
