"""Every statement the product layer runs against ``product_attribute_values``."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Attribute, AttributeOption
from app.models.product import ProductAttributeValue


async def list_for_product(
    session: AsyncSession, product_id: uuid.UUID
) -> list[tuple[ProductAttributeValue, Attribute, AttributeOption | None]]:
    """A product's values with their attribute, and their option when they have one."""

    statement = (
        select(ProductAttributeValue, Attribute, AttributeOption)
        .join(Attribute, Attribute.id == ProductAttributeValue.attribute_id)
        .outerjoin(
            AttributeOption, AttributeOption.id == ProductAttributeValue.option_id
        )
        .where(ProductAttributeValue.product_id == product_id)
        .order_by(Attribute.name)
    )
    return [(row[0], row[1], row[2]) for row in await session.execute(statement)]


async def attribute_ids_of(
    session: AsyncSession, product_id: uuid.UUID
) -> set[uuid.UUID]:
    rows = await session.execute(
        select(ProductAttributeValue.attribute_id).where(
            ProductAttributeValue.product_id == product_id
        )
    )
    return {row[0] for row in rows}


async def replace_values(
    session: AsyncSession,
    product_id: uuid.UUID,
    values: list[tuple[uuid.UUID, uuid.UUID | None, str | None, Decimal | None]],
) -> None:
    """Replace the product's whole set of values with ``values``.

    Each tuple is ``(attribute_id, option_id, value_text, value_number)``. Deleting
    first and inserting after is the "replace, do not merge" semantics the API
    promises.
    """

    await session.execute(
        delete(ProductAttributeValue).where(
            ProductAttributeValue.product_id == product_id
        )
    )
    session.add_all(
        ProductAttributeValue(
            product_id=product_id,
            attribute_id=attribute_id,
            option_id=option_id,
            value_text=value_text,
            value_number=value_number,
        )
        for attribute_id, option_id, value_text, value_number in values
    )
    await session.flush()
