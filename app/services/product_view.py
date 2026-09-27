"""Read-side assembly of a product and its children.

One place builds the nested shape a response needs, so ``ProductService`` and
``VariantService`` cannot disagree about it and the queries stay a fixed handful rather
than one per variant.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Attribute, AttributeOption
from app.models.product import (
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
)
from app.repositories import (
    product_attribute_value_repository,
    product_image_repository,
    variant_option_repository,
    variant_repository,
)


@dataclass(frozen=True, slots=True)
class VariantDetail:
    variant: ProductVariant
    options: list[tuple[Attribute, AttributeOption]]
    images: list[ProductImage]


@dataclass(frozen=True, slots=True)
class ProductDetail:
    product: Product
    values: list[tuple[ProductAttributeValue, Attribute, AttributeOption | None]]
    variants: list[VariantDetail]
    images: list[ProductImage]


async def variant_details(
    session: AsyncSession,
    variants: list[ProductVariant],
    images: list[ProductImage],
) -> list[VariantDetail]:
    """Attach each variant's options and images. ``images`` is the whole product's."""

    options = await variant_option_repository.options_by_variant(
        session, [variant.id for variant in variants]
    )
    by_variant: dict[uuid.UUID, list[ProductImage]] = {}
    for image in images:
        if image.variant_id is not None:
            by_variant.setdefault(image.variant_id, []).append(image)
    return [
        VariantDetail(
            variant, options.get(variant.id, []), by_variant.get(variant.id, [])
        )
        for variant in variants
    ]


async def load_detail(session: AsyncSession, product: Product) -> ProductDetail:
    values = await product_attribute_value_repository.list_for_product(
        session, product.id
    )
    variants = await variant_repository.list_variants(session, product.id)
    images = await product_image_repository.list_for_product(session, product.id)
    return ProductDetail(
        product=product,
        values=values,
        variants=await variant_details(session, variants, images),
        images=[image for image in images if image.variant_id is None],
    )


async def load_variant(
    session: AsyncSession, product_id: uuid.UUID, variant: ProductVariant
) -> VariantDetail:
    images = await product_image_repository.list_scope(session, product_id, variant.id)
    (detail,) = await variant_details(session, [variant], images)
    return detail
