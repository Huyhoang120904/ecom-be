"""Every statement the product layer runs against ``product_variant_options``."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Attribute, AttributeOption
from app.models.product import ProductVariantOption


async def create_options(
    session: AsyncSession,
    variant_id: uuid.UUID,
    pairs: list[tuple[uuid.UUID, uuid.UUID]],
) -> None:
    session.add_all(
        ProductVariantOption(
            variant_id=variant_id, attribute_id=attribute_id, option_id=option_id
        )
        for attribute_id, option_id in pairs
    )
    await session.flush()


async def options_by_variant(
    session: AsyncSession, variant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[Attribute, AttributeOption]]]:
    """Each variant's options with their attribute and option names, in name order."""

    grouped: dict[uuid.UUID, list[tuple[Attribute, AttributeOption]]] = {
        variant_id: [] for variant_id in variant_ids
    }
    if not variant_ids:
        return grouped
    statement = (
        select(ProductVariantOption.variant_id, Attribute, AttributeOption)
        .join(Attribute, Attribute.id == ProductVariantOption.attribute_id)
        .join(AttributeOption, AttributeOption.id == ProductVariantOption.option_id)
        .where(ProductVariantOption.variant_id.in_(variant_ids))
        .order_by(Attribute.name)
    )
    for variant_id, attribute, option in await session.execute(statement):
        grouped[variant_id].append((attribute, option))
    return grouped


async def attribute_ids_by_variant(
    session: AsyncSession, variant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
    """Just the attribute ids of each variant, which is all the publish rule needs."""

    grouped: dict[uuid.UUID, set[uuid.UUID]] = {v: set() for v in variant_ids}
    if not variant_ids:
        return {}
    rows = await session.execute(
        select(
            ProductVariantOption.variant_id, ProductVariantOption.attribute_id
        ).where(ProductVariantOption.variant_id.in_(variant_ids))
    )
    for variant_id, attribute_id in rows:
        grouped[variant_id].add(attribute_id)
    return {variant_id: frozenset(ids) for variant_id, ids in grouped.items()}
