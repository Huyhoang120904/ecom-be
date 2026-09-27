"""Category requests and payloads."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.catalog import (
    CATALOG_SLUG_MAX,
    CATEGORY_NAME_MAX,
    CATEGORY_NAME_MIN,
)
from app.utils import catalog as utils

POSITION_MAX = 100_000

Name = Annotated[str, Field(min_length=CATEGORY_NAME_MIN, max_length=CATEGORY_NAME_MAX)]
Position = Annotated[int, Field(ge=0, le=POSITION_MAX)]


def _normalize_name(value: str) -> str:
    return utils.normalize_text(
        value,
        field_name="category_name",
        minimum=CATEGORY_NAME_MIN,
        maximum=CATEGORY_NAME_MAX,
    )


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    parent_id: uuid.UUID | None = None
    position: Position = 0

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _normalize_name(value)


class CategoryUpdateRequest(BaseModel):
    """A partial update.

    ``parent_id`` distinguishes *absent* (leave the parent alone) from an explicit
    ``null`` (make this a root category), through ``model_fields_set``.
    """

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    parent_id: uuid.UUID | None = None
    position: Position | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_name(value)


class CategoryData(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str = Field(max_length=CATEGORY_NAME_MAX)
    slug: str = Field(max_length=CATALOG_SLUG_MAX)
    position: int
    is_leaf: bool


class CategoryTreeNode(BaseModel):
    """A category with its children nested, for rendering a picker."""

    id: uuid.UUID
    name: str = Field(max_length=CATEGORY_NAME_MAX)
    slug: str = Field(max_length=CATALOG_SLUG_MAX)
    position: int
    is_leaf: bool
    children: list[CategoryTreeNode]
