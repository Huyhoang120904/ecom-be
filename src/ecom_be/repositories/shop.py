"""Every statement the identity layer runs against ``shops``.

Nothing here commits; the service owns the transaction boundary. ``create_shop``
resolves a unique slug by lookup-then-insert, which is not atomic on its own -- the
partial unique index is the arbiter, and the service maps the resulting
``IntegrityError``.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.constants.identity import SLUG_FALLBACK
from ecom_be.models.identity import Shop
from ecom_be.utils.identity import slug_with_suffix, slugify


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


async def soft_delete_shop(session: AsyncSession, shop: Shop) -> None:
    shop.deleted_at = datetime.now(UTC)
    await session.flush()


async def list_all_shop_slugs(session: AsyncSession) -> set[str]:
    rows = await session.execute(select(Shop.slug))
    return {row[0] for row in rows}
