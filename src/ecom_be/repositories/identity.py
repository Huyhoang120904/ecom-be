"""Every statement the identity module executes.

Two rules hold throughout:

* This is the only layer that runs a statement. A service decides *what* should
  happen; this file is *how* it reaches the database.
* Nothing here commits. The request-scoped session is yielded with no implicit
  commit, so a service decides where a transaction ends. A repository that commits
  would make a multi-step use case impossible to keep atomic.

Reads filter ``deleted_at IS NULL`` explicitly rather than relying on a database
default or a session-level filter. The predicate is visible at each call site,
which is worth the repetition: a soft-delete filter that is invisible is the kind of
thing that ships a deleted row to a user.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Row, Select, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.constants.identity import SLUG_FALLBACK
from ecom_be.models.identity import (
    Membership,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    Shop,
    User,
)
from ecom_be.utils.identity import slug_with_suffix, slugify


def _rowcount(result: object) -> int:
    """Read a DML row count.

    SQLAlchemy types ``AsyncSession.execute`` as returning ``Result`` even for an
    ``update`` or ``delete``, where the runtime object is a ``CursorResult`` and does
    carry ``rowcount``. Narrowing in one place keeps the cast out of every call site.
    """

    if isinstance(result, CursorResult):
        return int(result.rowcount or 0)
    return 0


async def find_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Find a live user by email.

    ``email`` is a ``citext`` column, so the comparison is case-insensitive without
    this function doing anything, and a mixed-case row cannot exist because of the
    ``users_email_lower`` check.
    """

    statement: Select[tuple[User]] = select(User).where(
        User.email == email, User.deleted_at.is_(None)
    )
    return (await session.scalars(statement)).first()


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return (
        await session.scalars(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).first()


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str,
    full_name: str,
) -> User:
    user = User(email=email, password_hash=password_hash, full_name=full_name)
    session.add(user)
    await session.flush()
    return user


async def set_last_login(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(last_login_at=datetime.now(UTC))
    )


async def deactivate_user(session: AsyncSession, user: User) -> None:
    """Retire an account's ability to sign in without releasing its email."""

    user.deactivated_at = datetime.now(UTC)
    await session.flush()


async def soft_delete_user(session: AsyncSession, user: User) -> None:
    """Retire an account and release its email address for reuse."""

    user.deleted_at = datetime.now(UTC)
    await session.flush()


async def update_user_profile(
    session: AsyncSession, user: User, changes: dict[str, str | None]
) -> User:
    """Apply only the keys present in ``changes``.

    The caller is responsible for having decided which keys were supplied; an
    omitted key never reaches here, which is what makes "leave it alone" and "clear
    it" different outcomes rather than the same one.
    """

    for field, value in changes.items():
        setattr(user, field, value)
    await session.flush()
    return user


async def set_user_avatar_key(
    session: AsyncSession, user: User, key: str | None
) -> None:
    user.avatar_key = key
    user.avatar_updated_at = datetime.now(UTC) if key is not None else None
    await session.flush()


async def create_shop(session: AsyncSession, *, name: str) -> Shop:
    """Create a shop, suffixing the slug until it is unique.

    The lookup-then-insert is not atomic on its own. The partial unique index
    ``shops_slug_live`` is the arbiter, and the service maps the resulting
    ``IntegrityError`` rather than pretending this loop is a lock.
    """

    base = slugify(name) or SLUG_FALLBACK
    candidate = base
    suffix = 1
    while (
        await session.scalar(
            select(Shop.id).where(Shop.slug == candidate, Shop.deleted_at.is_(None))
        )
        is not None
    ):
        suffix += 1
        candidate = slug_with_suffix(base, suffix)

    shop = Shop(name=name, slug=candidate)
    session.add(shop)
    await session.flush()
    return shop


async def get_shop(session: AsyncSession, shop_id: uuid.UUID) -> Shop | None:
    return (
        await session.scalars(
            select(Shop).where(Shop.id == shop_id, Shop.deleted_at.is_(None))
        )
    ).first()


async def update_shop_profile(
    session: AsyncSession, shop: Shop, changes: dict[str, str | None]
) -> Shop:
    """Apply profile changes. ``slug`` is never among them."""

    for field, value in changes.items():
        setattr(shop, field, value)
    await session.flush()
    return shop


async def set_shop_background_key(
    session: AsyncSession, shop: Shop, key: str | None
) -> None:
    shop.background_key = key
    shop.background_updated_at = datetime.now(UTC) if key is not None else None
    await session.flush()


async def set_shop_active(
    session: AsyncSession, shop_id: uuid.UUID, active: bool
) -> None:
    """An operator action: suspend or restore a shop without deleting it."""

    await session.execute(
        update(Shop).where(Shop.id == shop_id).values(is_active=active)
    )


async def get_owner_role(session: AsyncSession) -> Role:
    """The seeded ``owner`` system role.

    Raises rather than returning ``None``: its absence means the seed migration has
    not run, which is a deployment state, not a request-level error.
    """

    role = (
        await session.scalars(
            select(Role).where(Role.key == "owner", Role.shop_id.is_(None))
        )
    ).first()
    if role is None:
        raise RuntimeError(
            "the owner system role is missing; run `alembic upgrade head`"
        )
    return role


async def get_role_by_key(session: AsyncSession, key: str) -> Role | None:
    return (
        await session.scalars(
            select(Role).where(Role.key == key, Role.shop_id.is_(None))
        )
    ).first()


async def create_membership(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    shop_id: uuid.UUID,
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

    user = await find_user_by_email(session, user_email)
    role = await get_role_by_key(session, role_key)
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


async def soft_delete_shop(session: AsyncSession, shop: Shop) -> None:
    shop.deleted_at = datetime.now(UTC)
    await session.flush()


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


async def create_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    active_shop_id: uuid.UUID | None,
    token_hash: str,
    expires_at: datetime,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> RefreshToken:
    token = RefreshToken(
        user_id=user_id,
        active_shop_id=active_shop_id,
        token_hash=token_hash,
        family_id=family_id or uuid.uuid4(),
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.add(token)
    await session.flush()
    return token


async def find_refresh_token(
    session: AsyncSession, token_hash: str
) -> RefreshToken | None:
    return (
        await session.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
    ).first()


async def revoke_refresh_token(
    session: AsyncSession, token: RefreshToken, replaced_by: RefreshToken | None = None
) -> None:
    token.revoked_at = datetime.now(UTC)
    if replaced_by is not None:
        token.replaced_by_id = replaced_by.id
    await session.flush()


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> int:
    """Revoke every unrevoked token in one family. Returns how many were revoked."""

    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    return _rowcount(result)


async def revoke_all_families_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> int:
    """Revoke every session an account holds, not just the current one.

    Used by deactivation: a deactivated account must not keep a live session
    anywhere.
    """

    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return _rowcount(result)


async def revoke_families_for_shop(session: AsyncSession, shop_id: uuid.UUID) -> int:
    """Revoke the sessions whose active shop is this one.

    Deleting a shop ends the sessions that were scoped to it, which is what makes
    their next request a clean "that shop is gone" rather than a lingering token
    pointing at nothing.
    """

    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.active_shop_id == shop_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    return _rowcount(result)


async def list_unrevoked_family(
    session: AsyncSession, family_id: uuid.UUID
) -> list[RefreshToken]:
    rows = await session.execute(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    return list(rows.scalars())


async def delete_expired_refresh_tokens(session: AsyncSession) -> int:
    """Lazily prune rows past expiry.

    Called by the login and refresh paths rather than by a scheduled job: those are
    the two moments the table is already being written, so the cleanup rides on work
    that is happening anyway.
    """

    result = await session.execute(
        delete(RefreshToken).where(RefreshToken.expires_at <= datetime.now(UTC))
    )
    return _rowcount(result)


async def list_all_shop_slugs(session: AsyncSession) -> set[str]:
    rows = await session.execute(select(Shop.slug))
    return {row[0] for row in rows}


async def list_permission_keys(session: AsyncSession) -> set[str]:
    rows = await session.execute(select(Permission.key))
    return {row[0] for row in rows}
