"""Every statement the product layer runs against ``product_variants``.

Only *live* variants (``deleted_at IS NULL``) are ever returned. A soft-deleted
variant's row and its options are kept, but nothing here reads them back.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import ProductVariant


async def create_variant(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    shop_id: uuid.UUID,
    sku_code: str,
    price: int,
    stock: int,
    status: str,
    option_key: str,
) -> ProductVariant:
    variant = ProductVariant(
        product_id=product_id,
        shop_id=shop_id,
        sku_code=sku_code,
        price=price,
        stock=stock,
        status=status,
        option_key=option_key,
    )
    session.add(variant)
    await session.flush()
    return variant


async def get_variant(
    session: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID
) -> ProductVariant | None:
    return (
        await session.scalars(
            select(ProductVariant).where(
                ProductVariant.id == variant_id,
                ProductVariant.product_id == product_id,
                ProductVariant.deleted_at.is_(None),
            )
        )
    ).first()


async def list_variants(
    session: AsyncSession, product_id: uuid.UUID
) -> list[ProductVariant]:
    statement = (
        select(ProductVariant)
        .where(
            ProductVariant.product_id == product_id,
            ProductVariant.deleted_at.is_(None),
        )
        .order_by(ProductVariant.created_at, ProductVariant.id)
    )
    return list((await session.scalars(statement)).all())


async def update_variant(
    session: AsyncSession, variant: ProductVariant, changes: dict[str, object]
) -> ProductVariant:
    for field, value in changes.items():
        setattr(variant, field, value)
    await session.flush()
    return variant


async def soft_delete_variant(
    session: AsyncSession, variant: ProductVariant, when: datetime
) -> None:
    variant.deleted_at = when
    await session.flush()


async def soft_delete_variants_of_product(
    session: AsyncSession, product_id: uuid.UUID, when: datetime
) -> None:
    """Cascade a product's soft delete to its live variants with one timestamp."""

    await session.execute(
        update(ProductVariant)
        .where(
            ProductVariant.product_id == product_id,
            ProductVariant.deleted_at.is_(None),
        )
        .values(deleted_at=when)
    )
