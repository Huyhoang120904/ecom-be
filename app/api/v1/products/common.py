"""Shared dependencies and response mappers for the product routers."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_application_db_session, require_permissions
from app.api.media_urls import product_image_url
from app.api.principal import Principal
from app.constants.catalog import (
    PRODUCTS_READ,
    PRODUCTS_WRITE,
    AttributeDataType,
    ProductStatus,
    VariantStatus,
)
from app.models.product import Product, ProductImage
from app.schemas.product import (
    AttributeValueRequest,
    ImageData,
    ProductAttributeData,
    ProductData,
    ProductSummary,
    VariantData,
    VariantOptionData,
)
from app.services.product_view import ProductDetail, VariantDetail
from app.utils.catalog import AttributeValueInput

# Reading needs ``products:read`` (viewer and up); writing needs ``products:write``
# (manager and owner). The shop is always the caller's active shop, from the token.
Reader = Annotated[Principal, Depends(require_permissions(PRODUCTS_READ))]
Writer = Annotated[Principal, Depends(require_permissions(PRODUCTS_WRITE))]

Session = Annotated[AsyncSession, Depends(get_application_db_session)]


def shop_of(principal: Principal) -> uuid.UUID:
    return uuid.UUID(principal.active_shop_id)


def user_of(principal: Principal) -> uuid.UUID:
    return uuid.UUID(principal.user_id)


def value_inputs(values: list[AttributeValueRequest]) -> list[AttributeValueInput]:
    """Requests to the service's input type; a float becomes an exact ``Decimal``."""

    from decimal import Decimal

    return [
        AttributeValueInput(
            attribute_id=value.attribute_id,
            option_id=value.option_id,
            value_text=value.value_text,
            value_number=(
                Decimal(str(value.value_number))
                if value.value_number is not None
                else None
            ),
        )
        for value in values
    ]


def image_data(image: ProductImage, request: Request) -> ImageData:
    return ImageData(
        id=image.id,
        variant_id=image.variant_id,
        position=image.position,
        url=product_image_url(image, request),
    )


def variant_data(detail: VariantDetail, request: Request) -> VariantData:
    variant = detail.variant
    return VariantData(
        id=variant.id,
        product_id=variant.product_id,
        sku_code=variant.sku_code,
        price=variant.price,
        stock=variant.stock,
        status=VariantStatus(variant.status),
        options=[
            VariantOptionData(
                attribute_id=attribute.id,
                attribute_name=attribute.name,
                option_id=option.id,
                option_value=option.value,
            )
            for attribute, option in detail.options
        ],
        images=[image_data(image, request) for image in detail.images],
    )


def product_data(detail: ProductDetail, request: Request) -> ProductData:
    product = detail.product
    return ProductData(
        id=product.id,
        category_id=product.category_id,
        brand_id=product.brand_id,
        name=product.name,
        description=product.description,
        status=ProductStatus(product.status),
        created_at=product.created_at,
        updated_at=product.updated_at,
        attributes=[
            ProductAttributeData(
                attribute_id=attribute.id,
                name=attribute.name,
                type=AttributeDataType(attribute.data_type),
                option_id=value.option_id,
                option_value=option.value if option is not None else None,
                value_text=value.value_text,
                value_number=(
                    float(value.value_number)
                    if value.value_number is not None
                    else None
                ),
            )
            for value, attribute, option in detail.values
        ],
        variants=[variant_data(variant, request) for variant in detail.variants],
        images=[image_data(image, request) for image in detail.images],
    )


def product_summary(product: Product) -> ProductSummary:
    return ProductSummary(
        id=product.id,
        category_id=product.category_id,
        brand_id=product.brand_id,
        name=product.name,
        status=ProductStatus(product.status),
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
