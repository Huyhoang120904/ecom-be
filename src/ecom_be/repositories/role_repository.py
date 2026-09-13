"""Statements against ``roles`` and ``permissions``.

Both are read-only lookup tables here: roles arrive from the seed migration and
permissions are the vocabulary those roles grant. Writing them is a migration, not a
request, so this module has no writes.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.models.identity import Permission, Role


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


async def list_permission_keys(session: AsyncSession) -> set[str]:
    rows = await session.execute(select(Permission.key))
    return {row[0] for row in rows}
