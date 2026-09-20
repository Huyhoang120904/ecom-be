"""Every statement the catalog layer runs against ``brands``.

Nothing here commits. ``create_brand`` resolves a unique slug by lookup-then-insert,
which is not atomic on its own; the unique constraints are the arbiter and the service
maps the resulting ``IntegrityError``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Brand
from app.models.product import Product
from app.utils.catalog import slug_with_suffix, slugify


async def create_brand(session: AsyncSession, *, name: str) -> Brand:
    base = slugify(name)
    candidate = base
    suffix = 1
    while (
        await session.scalar(select(Brand.id).where(Brand.slug == candidate))
    ) is not None:
        suffix += 1
        candidate = slug_with_suffix(base, suffix)

    brand = Brand(name=name, slug=candidate)
    session.add(brand)
    await session.flush()
    return brand


async def get_brand(session: AsyncSession, brand_id: uuid.UUID) -> Brand | None:
    return await session.get(Brand, brand_id)


async def list_brands(session: AsyncSession) -> list[Brand]:
    return list((await session.scalars(select(Brand).order_by(Brand.name))).all())


async def rename_brand(session: AsyncSession, brand: Brand, name: str) -> Brand:
    """Change the name. The slug is deliberately left alone."""

    brand.name = name
    await session.flush()
    return brand


async def delete_brand(session: AsyncSession, brand_id: uuid.UUID) -> None:
    await session.execute(delete(Brand).where(Brand.id == brand_id))


async def brand_has_products(session: AsyncSession, brand_id: uuid.UUID) -> bool:
    """Any product row at all, soft deleted included: the foreign key sees them too."""

    return bool(
        await session.scalar(select(exists().where(Product.brand_id == brand_id)))
    )
