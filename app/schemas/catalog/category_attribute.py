"""A category's attribute configuration: the metadata a client builds a form from."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.constants.catalog import (
    ATTRIBUTE_KEY_MAX,
    ATTRIBUTE_NAME_MAX,
    AttributeDataType,
)
from app.schemas.catalog.attribute import OptionData

POSITION_MAX = 100_000


class CategoryAttributeRequest(BaseModel):
    """Attach an attribute to a category, or replace its flags (PUT is idempotent)."""

    model_config = ConfigDict(extra="forbid")

    required: bool = False
    filterable: bool = False
    searchable: bool = False
    is_variation: bool = False
    position: Annotated[int, Field(ge=0, le=POSITION_MAX)] = 0


class CategoryAttributeData(BaseModel):
    """One attribute as a category asks for it.

    ``id`` is the *attribute's* id: that is what a product's attribute values and a
    variant's options refer to. ``type`` is the attribute's ``data_type`` and
    ``options`` is filled for ``SELECT`` attributes only.
    """

    id: uuid.UUID
    key: str = Field(max_length=ATTRIBUTE_KEY_MAX)
    name: str = Field(max_length=ATTRIBUTE_NAME_MAX)
    type: AttributeDataType
    required: bool
    filterable: bool
    searchable: bool
    is_variation: bool
    position: int
    options: list[OptionData]
