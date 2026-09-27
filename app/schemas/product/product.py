"""Product requests and payloads."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.constants.catalog import (
    ATTRIBUTE_NAME_MAX,
    ATTRIBUTE_VALUES_MAX,
    OPTION_VALUE_MAX,
    PRODUCT_DESCRIPTION_MAX,
    PRODUCT_NAME_MAX,
    PRODUCT_NAME_MIN,
    VALUE_NUMBER_ABS_MAX,
    VALUE_TEXT_MAX,
    AttributeDataType,
    ProductStatus,
)
from app.schemas.product.image import ImageData
from app.schemas.product.variant import VariantData
from app.utils import catalog as utils

Name = Annotated[str, Field(min_length=PRODUCT_NAME_MIN, max_length=PRODUCT_NAME_MAX)]
Description = Annotated[str, Field(max_length=PRODUCT_DESCRIPTION_MAX)]
Number = Annotated[
    float,
    Field(ge=-VALUE_NUMBER_ABS_MAX, le=VALUE_NUMBER_ABS_MAX, allow_inf_nan=False),
]


def _name(value: str) -> str:
    return utils.normalize_text(
        value,
        field_name="product_name",
        minimum=PRODUCT_NAME_MIN,
        maximum=PRODUCT_NAME_MAX,
    )


def _description(value: str) -> str:
    return utils.normalize_text(
        value,
        field_name="product_description",
        minimum=0,
        maximum=PRODUCT_DESCRIPTION_MAX,
        multiline=True,
    )


class AttributeValueRequest(BaseModel):
    """One attribute's value: exactly the field its ``data_type`` asks for."""

    model_config = ConfigDict(extra="forbid")

    attribute_id: uuid.UUID
    option_id: uuid.UUID | None = None
    value_text: Annotated[str | None, Field(max_length=VALUE_TEXT_MAX)] = None
    value_number: Number | None = None


class ProductCreateRequest(BaseModel):
    """Create a product. It always starts as a ``draft``: there is no ``status``."""

    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    name: Name
    description: Description | None = None
    attributes: Annotated[
        list[AttributeValueRequest], Field(max_length=ATTRIBUTE_VALUES_MAX)
    ] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return _name(value)

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        return None if value is None else (_description(value) or None)


class ProductUpdateRequest(BaseModel):
    """A partial update.

    ``status`` and ``category_id`` are not fields, so sending them is a ``422``: a
    status moves only through ``publish``/``unpublish`` and a product never changes
    category.

    ``attributes`` absent leaves the values alone, ``[]`` clears them all, and a list
    replaces the whole set. ``brand_id`` and ``description`` accept an explicit ``null``
    to clear them, told apart from *absent* through ``model_fields_set``.
    """

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Description | None = None
    brand_id: uuid.UUID | None = None
    attributes: (
        Annotated[list[AttributeValueRequest], Field(max_length=ATTRIBUTE_VALUES_MAX)]
        | None
    ) = None

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        return None if value is None else _name(value)

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        return None if value is None else (_description(value) or None)

    @model_validator(mode="after")
    def _attributes_is_a_list_or_absent(self) -> Self:
        if "attributes" in self.model_fields_set and self.attributes is None:
            raise ValueError("attributes must be a list; omit it to keep the values")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class ProductAttributeData(BaseModel):
    attribute_id: uuid.UUID
    name: str = Field(max_length=ATTRIBUTE_NAME_MAX)
    type: AttributeDataType
    option_id: uuid.UUID | None
    option_value: str | None = Field(max_length=OPTION_VALUE_MAX)
    value_text: str | None = Field(max_length=VALUE_TEXT_MAX)
    value_number: float | None


class ProductData(BaseModel):
    """A product with everything that hangs off it."""

    id: uuid.UUID
    category_id: uuid.UUID
    brand_id: uuid.UUID | None
    name: str = Field(max_length=PRODUCT_NAME_MAX)
    description: str | None = Field(max_length=PRODUCT_DESCRIPTION_MAX)
    status: ProductStatus
    created_at: dt.datetime
    updated_at: dt.datetime
    attributes: list[ProductAttributeData]
    variants: list[VariantData]
    images: list[ImageData]


class ProductSummary(BaseModel):
    """A product as a list row: no children."""

    id: uuid.UUID
    category_id: uuid.UUID
    brand_id: uuid.UUID | None
    name: str = Field(max_length=PRODUCT_NAME_MAX)
    status: ProductStatus
    created_at: dt.datetime
    updated_at: dt.datetime


class ProductPage(BaseModel):
    items: list[ProductSummary]
    total: int
    page: int
    page_size: int
