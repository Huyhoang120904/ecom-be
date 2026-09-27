"""Variant (SKU) requests and payload."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.catalog import (
    ATTRIBUTE_NAME_MAX,
    OPTION_VALUE_MAX,
    PRICE_MAX,
    SKU_CODE_MAX,
    SKU_CODE_MIN,
    STOCK_MAX,
    VARIANT_OPTIONS_MAX,
    VariantStatus,
)
from app.schemas.product.image import ImageData
from app.utils import catalog as utils

SkuCode = Annotated[str, Field(min_length=SKU_CODE_MIN, max_length=SKU_CODE_MAX)]
Price = Annotated[int, Field(ge=0, le=PRICE_MAX)]
Stock = Annotated[int, Field(ge=0, le=STOCK_MAX)]


def _sku(value: str) -> str:
    return utils.normalize_text(
        value, field_name="sku_code", minimum=SKU_CODE_MIN, maximum=SKU_CODE_MAX
    )


class VariantOptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute_id: uuid.UUID
    option_id: uuid.UUID


class VariantCreateRequest(BaseModel):
    """Create a variant. ``options`` fixes what it *is* and cannot be edited later."""

    model_config = ConfigDict(extra="forbid")

    sku_code: SkuCode
    price: Price
    stock: Stock = 0
    status: VariantStatus = VariantStatus.ACTIVE
    options: Annotated[
        list[VariantOptionRequest], Field(max_length=VARIANT_OPTIONS_MAX)
    ] = Field(default_factory=list)

    @field_validator("sku_code")
    @classmethod
    def _normalize_sku(cls, value: str) -> str:
        return _sku(value)


class VariantUpdateRequest(BaseModel):
    """A partial update. ``options`` is rejected: delete and recreate to change them."""

    model_config = ConfigDict(extra="forbid")

    sku_code: SkuCode | None = None
    price: Price | None = None
    stock: Stock | None = None
    status: VariantStatus | None = None

    @field_validator("sku_code")
    @classmethod
    def _normalize_sku(cls, value: str | None) -> str | None:
        return None if value is None else _sku(value)


class VariantOptionData(BaseModel):
    attribute_id: uuid.UUID
    attribute_name: str = Field(max_length=ATTRIBUTE_NAME_MAX)
    option_id: uuid.UUID
    option_value: str = Field(max_length=OPTION_VALUE_MAX)


class VariantData(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    sku_code: str = Field(max_length=SKU_CODE_MAX)
    price: int
    stock: int
    status: VariantStatus
    options: list[VariantOptionData]
    images: list[ImageData]
