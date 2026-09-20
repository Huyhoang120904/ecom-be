"""Every statement the catalog layer runs against ``category_attributes``."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Attribute, CategoryAttribute
from app.models.product import (
    Product,
    ProductAttributeValue,
    ProductVariant,
    ProductVariantOption,
)


async def get_config(
    session: AsyncSession, category_id: uuid.UUID, attribute_id: uuid.UUID
) -> CategoryAttribute | None:
    return await session.get(CategoryAttribute, (category_id, attribute_id))


async def list_for_category(
    session: AsyncSession, category_id: uuid.UUID
) -> list[tuple[CategoryAttribute, Attribute]]:
    """The category's configuration with each attribute, in display order."""

    statement = (
        select(CategoryAttribute, Attribute)
        .join(Attribute, Attribute.id == CategoryAttribute.attribute_id)
        .where(CategoryAttribute.category_id == category_id)
        .order_by(CategoryAttribute.position, Attribute.name)
    )
    return [(row[0], row[1]) for row in await session.execute(statement)]


async def upsert_config(
    session: AsyncSession,
    *,
    category_id: uuid.UUID,
    attribute_id: uuid.UUID,
    values: dict[str, object],
) -> CategoryAttribute:
    """Attach the attribute, or update the flags when it is already attached."""

    config = await get_config(session, category_id, attribute_id)
    if config is None:
        config = CategoryAttribute(
            category_id=category_id, attribute_id=attribute_id, **values
        )
        session.add(config)
    else:
        for field, value in values.items():
            setattr(config, field, value)
    await session.flush()
    return config


async def delete_config(
    session: AsyncSession, category_id: uuid.UUID, attribute_id: uuid.UUID
) -> None:
    await session.execute(
        delete(CategoryAttribute).where(
            CategoryAttribute.category_id == category_id,
            CategoryAttribute.attribute_id == attribute_id,
        )
    )


async def used_in_category(
    session: AsyncSession, category_id: uuid.UUID, attribute_id: uuid.UUID
) -> bool:
    """Whether a product of this category has a value or a variant option for it.

    Scoped to the category, unlike ``attribute_in_use``: detaching an attribute here
    only matters to this category's products. Soft-deleted products and variants
    count, since their rows are kept.
    """

    valued = await session.scalar(
        select(
            exists().where(
                ProductAttributeValue.attribute_id == attribute_id,
                ProductAttributeValue.product_id == Product.id,
                Product.category_id == category_id,
            )
        )
    )
    if valued:
        return True
    return bool(
        await session.scalar(
            select(
                exists().where(
                    ProductVariantOption.attribute_id == attribute_id,
                    ProductVariantOption.variant_id == ProductVariant.id,
                    ProductVariant.product_id == Product.id,
                    Product.category_id == category_id,
                )
            )
        )
    )
