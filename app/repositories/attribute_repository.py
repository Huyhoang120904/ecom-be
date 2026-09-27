"""Every statement the catalog layer runs against ``attributes``."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Attribute, CategoryAttribute
from app.models.product import ProductAttributeValue, ProductVariantOption


async def create_attribute(
    session: AsyncSession, *, key: str, name: str, data_type: str
) -> Attribute:
    attribute = Attribute(key=key, name=name, data_type=data_type)
    session.add(attribute)
    await session.flush()
    return attribute


async def get_attribute(
    session: AsyncSession, attribute_id: uuid.UUID
) -> Attribute | None:
    return await session.get(Attribute, attribute_id)


async def get_attributes(
    session: AsyncSession, attribute_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Attribute]:
    if not attribute_ids:
        return {}
    rows = await session.scalars(
        select(Attribute).where(Attribute.id.in_(attribute_ids))
    )
    return {attribute.id: attribute for attribute in rows}


async def list_attributes(session: AsyncSession) -> list[Attribute]:
    statement = select(Attribute).order_by(Attribute.name)
    return list((await session.scalars(statement)).all())


async def rename_attribute(
    session: AsyncSession, attribute: Attribute, name: str
) -> Attribute:
    """Change the display name. ``key`` and ``data_type`` are immutable."""

    attribute.name = name
    await session.flush()
    return attribute


async def delete_attribute(session: AsyncSession, attribute_id: uuid.UUID) -> None:
    await session.execute(delete(Attribute).where(Attribute.id == attribute_id))


async def attribute_is_attached(session: AsyncSession, attribute_id: uuid.UUID) -> bool:
    return bool(
        await session.scalar(
            select(exists().where(CategoryAttribute.attribute_id == attribute_id))
        )
    )


async def attribute_in_use(session: AsyncSession, attribute_id: uuid.UUID) -> bool:
    """*Valued* or *varied*: some product value or variant option references it.

    Soft-deleted products and variants count, because their rows are kept and the
    ``RESTRICT`` foreign keys see them.
    """

    valued = await session.scalar(
        select(exists().where(ProductAttributeValue.attribute_id == attribute_id))
    )
    if valued:
        return True
    return bool(
        await session.scalar(
            select(exists().where(ProductVariantOption.attribute_id == attribute_id))
        )
    )
