"""Every statement the product layer runs against ``product_images``.

An image row is *hard* deleted along with its variant or product, so unlike variants
there is no ``deleted_at`` to filter on.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import ProductImage


async def create_image(
    session: AsyncSession,
    *,
    image_id: uuid.UUID,
    product_id: uuid.UUID,
    variant_id: uuid.UUID | None,
    key: str,
    position: int,
) -> ProductImage:
    image = ProductImage(
        id=image_id,
        product_id=product_id,
        variant_id=variant_id,
        key=key,
        position=position,
    )
    session.add(image)
    await session.flush()
    return image


async def get_image(session: AsyncSession, image_id: uuid.UUID) -> ProductImage | None:
    """An image by id alone, for the public media route, which is not shop-scoped."""

    return await session.get(ProductImage, image_id)


async def get_product_image(
    session: AsyncSession, product_id: uuid.UUID, image_id: uuid.UUID
) -> ProductImage | None:
    return (
        await session.scalars(
            select(ProductImage).where(
                ProductImage.id == image_id, ProductImage.product_id == product_id
            )
        )
    ).first()


def _scope(variant_id: uuid.UUID | None):  # type: ignore[no-untyped-def]
    return (
        ProductImage.variant_id.is_(None)
        if variant_id is None
        else ProductImage.variant_id == variant_id
    )


async def list_scope(
    session: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID | None
) -> list[ProductImage]:
    """The images of one scope (the product's own, or one variant's), in order."""

    statement = (
        select(ProductImage)
        .where(ProductImage.product_id == product_id, _scope(variant_id))
        .order_by(ProductImage.position, ProductImage.created_at)
    )
    return list((await session.scalars(statement)).all())


async def count_scope(
    session: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID | None
) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(ProductImage)
        .where(ProductImage.product_id == product_id, _scope(variant_id))
    )
    return int(total or 0)


async def list_for_product(
    session: AsyncSession, product_id: uuid.UUID
) -> list[ProductImage]:
    statement = (
        select(ProductImage)
        .where(ProductImage.product_id == product_id)
        .order_by(ProductImage.position, ProductImage.created_at)
    )
    return list((await session.scalars(statement)).all())


async def set_positions(session: AsyncSession, ordered: list[ProductImage]) -> None:
    """Rewrite positions as ``0..n-1`` in the given order."""

    for position, image in enumerate(ordered):
        image.position = position
    await session.flush()


async def delete_image(session: AsyncSession, image: ProductImage) -> None:
    await session.delete(image)
    await session.flush()


async def delete_for_variant(
    session: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID
) -> list[str]:
    """Hard delete a variant's images and return their storage keys."""

    keys = list(
        (
            await session.scalars(
                select(ProductImage.key).where(
                    ProductImage.product_id == product_id,
                    ProductImage.variant_id == variant_id,
                )
            )
        ).all()
    )
    await session.execute(
        delete(ProductImage).where(
            ProductImage.product_id == product_id,
            ProductImage.variant_id == variant_id,
        )
    )
    return keys


async def delete_for_product(session: AsyncSession, product_id: uuid.UUID) -> list[str]:
    """Hard delete every image of a product and return their storage keys."""

    keys = list(
        (
            await session.scalars(
                select(ProductImage.key).where(ProductImage.product_id == product_id)
            )
        ).all()
    )
    await session.execute(
        delete(ProductImage).where(ProductImage.product_id == product_id)
    )
    return keys
