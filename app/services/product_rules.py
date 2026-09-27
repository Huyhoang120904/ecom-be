"""The one place that decides whether a product may be ``active``.

``enforce_product_invariants`` is called by ``publish`` and by every mutation of a
product that is already active (its attribute values, its variants). Sharing one
function is the point: a rule copied into each caller is a rule that drifts, and the
plan's whole promise is that no path around ``publish`` exists.

The invariants are enforced *at those moments*, not continuously. A change to the
catalog (a new required attribute on the category) can leave an active product stale;
it stays active until its seller next changes it, and only then is it asked to comply.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors.catalog import MissingItem, ProductInvariantViolated
from app.models.product import Product
from app.repositories import (
    category_attribute_repository,
    product_attribute_value_repository,
    variant_option_repository,
    variant_repository,
)
from app.utils.catalog import (
    CategoryAttributeRule,
    Gaps,
    VariantShape,
    published_gaps,
)


async def product_gaps(session: AsyncSession, product: Product) -> Gaps:
    """What the product still lacks to satisfy the published invariants."""

    configuration = await category_attribute_repository.list_for_category(
        session, product.category_id
    )
    rules = [
        CategoryAttributeRule(
            attribute_id=attribute.id,
            name=attribute.name,
            required=config.required,
            is_variation=config.is_variation,
        )
        for config, attribute in configuration
    ]
    value_ids = await product_attribute_value_repository.attribute_ids_of(
        session, product.id
    )
    variants = await variant_repository.list_variants(session, product.id)
    attribute_ids = await variant_option_repository.attribute_ids_by_variant(
        session, [variant.id for variant in variants]
    )
    shapes = [
        VariantShape(
            status=variant.status,
            attribute_ids=attribute_ids.get(variant.id, frozenset()),
        )
        for variant in variants
    ]
    return published_gaps(rules=rules, value_attribute_ids=value_ids, variants=shapes)


async def enforce_product_invariants(session: AsyncSession, product: Product) -> None:
    """Raise ``ProductInvariantViolated`` unless the product may be ``active``."""

    gaps = await product_gaps(session, product)
    if not gaps.is_empty():
        missing: list[MissingItem] = [
            {
                "attribute_id": item["attribute_id"],
                "name": item["name"],
                "where": item["where"],
            }
            for item in gaps.missing
        ]
        raise ProductInvariantViolated(missing, reasons=gaps.reasons)
