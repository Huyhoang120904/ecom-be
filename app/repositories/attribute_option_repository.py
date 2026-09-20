"""Every statement the catalog layer runs against ``attribute_options``."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import AttributeOption
from app.models.product import ProductAttributeValue, ProductVariantOption


async def create_option(
    session: AsyncSession, *, attribute_id: uuid.UUID, value: str, sort_order: int
) -> AttributeOption:
    option = AttributeOption(
        attribute_id=attribute_id, value=value, sort_order=sort_order
    )
    session.add(option)
    await session.flush()
    return option


async def get_option(
    session: AsyncSession, attribute_id: uuid.UUID, option_id: uuid.UUID
) -> AttributeOption | None:
    return (
        await session.scalars(
            select(AttributeOption).where(
                AttributeOption.id == option_id,
                AttributeOption.attribute_id == attribute_id,
            )
        )
    ).first()


async def list_options(
    session: AsyncSession, attribute_id: uuid.UUID
) -> list[AttributeOption]:
    statement = (
        select(AttributeOption)
        .where(AttributeOption.attribute_id == attribute_id)
        .order_by(AttributeOption.sort_order, AttributeOption.value)
    )
    return list((await session.scalars(statement)).all())


async def list_options_for_attributes(
    session: AsyncSession, attribute_ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[AttributeOption]]:
    grouped: dict[uuid.UUID, list[AttributeOption]] = {a: [] for a in attribute_ids}
    if not attribute_ids:
        return grouped
    statement = (
        select(AttributeOption)
        .where(AttributeOption.attribute_id.in_(attribute_ids))
        .order_by(AttributeOption.sort_order, AttributeOption.value)
    )
    for option in await session.scalars(statement):
        grouped[option.attribute_id].append(option)
    return grouped


async def option_ids_of(
    session: AsyncSession, attribute_id: uuid.UUID
) -> set[uuid.UUID]:
    rows = await session.execute(
        select(AttributeOption.id).where(AttributeOption.attribute_id == attribute_id)
    )
    return {row[0] for row in rows}


async def update_option(
    session: AsyncSession, option: AttributeOption, changes: dict[str, object]
) -> AttributeOption:
    for field, value in changes.items():
        setattr(option, field, value)
    await session.flush()
    return option


async def delete_option(session: AsyncSession, option_id: uuid.UUID) -> None:
    await session.execute(
        delete(AttributeOption).where(AttributeOption.id == option_id)
    )


async def option_in_use(session: AsyncSession, option_id: uuid.UUID) -> bool:
    """Referenced by a product value or a variant option, soft-deleted parents too."""

    valued = await session.scalar(
        select(exists().where(ProductAttributeValue.option_id == option_id))
    )
    if valued:
        return True
    return bool(
        await session.scalar(
            select(exists().where(ProductVariantOption.option_id == option_id))
        )
    )
