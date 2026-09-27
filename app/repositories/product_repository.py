"""Every statement the product layer runs against ``products``.

Every lookup takes the ``shop_id``: a product is only ever found *through* a shop, so a
caller cannot name a product of another shop even by guessing its id. Nothing here
commits.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


async def create_product(
    session: AsyncSession,
    *,
    shop_id: uuid.UUID,
    category_id: uuid.UUID,
    brand_id: uuid.UUID | None,
    name: str,
    description: str | None,
    user_id: uuid.UUID,
) -> Product:
    product = Product(
        shop_id=shop_id,
        category_id=category_id,
        brand_id=brand_id,
        name=name,
        description=description,
        status="draft",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    session.add(product)
    await session.flush()
    return product


async def get_product(
    session: AsyncSession,
    shop_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    lock: bool = False,
) -> Product | None:
    """A live product of this shop, optionally locked ``FOR UPDATE``.

    The lock is what serialises every write to a product's variants, values and
    status, so their cross-row checks cannot race each other.
    """

    statement = select(Product).where(
        Product.id == product_id,
        Product.shop_id == shop_id,
        Product.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    return (await session.scalars(statement)).first()


async def list_products(
    session: AsyncSession,
    shop_id: uuid.UUID,
    *,
    status: str | None,
    offset: int,
    limit: int,
) -> tuple[list[Product], int]:
    conditions = [Product.shop_id == shop_id, Product.deleted_at.is_(None)]
    if status is not None:
        conditions.append(Product.status == status)
    total = await session.scalar(
        select(func.count()).select_from(Product).where(*conditions)
    )
    rows = await session.scalars(
        select(Product)
        .where(*conditions)
        .order_by(Product.created_at.desc(), Product.id)
        .offset(offset)
        .limit(limit)
    )
    return list(rows.all()), int(total or 0)


async def update_product(
    session: AsyncSession,
    product: Product,
    changes: dict[str, object],
    *,
    user_id: uuid.UUID,
) -> Product:
    for field, value in changes.items():
        setattr(product, field, value)
    product.updated_by_user_id = user_id
    # Set explicitly: replacing attribute values alone changes no product column, and
    # an ORM ``onupdate`` only fires when the row itself is updated.
    product.updated_at = now()
    await session.flush()
    return product


async def set_status(
    session: AsyncSession, product: Product, status: str, *, user_id: uuid.UUID
) -> None:
    product.status = status
    product.updated_by_user_id = user_id
    product.updated_at = now()
    await session.flush()


async def soft_delete_product(
    session: AsyncSession, product: Product, *, user_id: uuid.UUID, when: datetime
) -> None:
    product.deleted_at = when
    product.updated_by_user_id = user_id
    await session.flush()


def now() -> datetime:
    return datetime.now(UTC)
