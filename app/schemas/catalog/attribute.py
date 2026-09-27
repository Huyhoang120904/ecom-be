"""Attribute and option requests and payloads."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.catalog import (
    ATTRIBUTE_KEY_MAX,
    ATTRIBUTE_KEY_MIN,
    ATTRIBUTE_NAME_MAX,
    ATTRIBUTE_NAME_MIN,
    OPTION_VALUE_MAX,
    OPTION_VALUE_MIN,
    AttributeDataType,
)
from app.utils import catalog as utils

SORT_MAX = 100_000

Name = Annotated[
    str, Field(min_length=ATTRIBUTE_NAME_MIN, max_length=ATTRIBUTE_NAME_MAX)
]
OptionValue = Annotated[
    str, Field(min_length=OPTION_VALUE_MIN, max_length=OPTION_VALUE_MAX)
]
SortOrder = Annotated[int, Field(ge=0, le=SORT_MAX)]


def _name(value: str) -> str:
    return utils.normalize_text(
        value,
        field_name="attribute_name",
        minimum=ATTRIBUTE_NAME_MIN,
        maximum=ATTRIBUTE_NAME_MAX,
    )


def _option_value(value: str) -> str:
    return utils.normalize_text(
        value,
        field_name="option_value",
        minimum=OPTION_VALUE_MIN,
        maximum=OPTION_VALUE_MAX,
    )


class AttributeCreateRequest(BaseModel):
    """``key`` and ``data_type`` are chosen here and never change afterwards."""

    model_config = ConfigDict(extra="forbid")

    key: Annotated[
        str,
        Field(
            min_length=ATTRIBUTE_KEY_MIN,
            max_length=ATTRIBUTE_KEY_MAX,
            pattern=r"^[a-z][a-z0-9_]*$",
        ),
    ]
    name: Name
    data_type: AttributeDataType

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return _name(value)


class AttributeUpdateRequest(BaseModel):
    """Only the display name changes. ``key`` and ``data_type`` are rejected (422)."""

    model_config = ConfigDict(extra="forbid")

    name: Name

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return _name(value)


class OptionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: OptionValue
    sort_order: SortOrder | None = None

    @field_validator("value")
    @classmethod
    def _normalize_value(cls, value: str) -> str:
        return _option_value(value)


class OptionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: OptionValue | None = None
    sort_order: SortOrder | None = None

    @field_validator("value")
    @classmethod
    def _normalize_value(cls, value: str | None) -> str | None:
        return None if value is None else _option_value(value)


class OptionData(BaseModel):
    id: uuid.UUID
    value: str = Field(max_length=OPTION_VALUE_MAX)
    sort_order: int


class AttributeData(BaseModel):
    id: uuid.UUID
    key: str = Field(max_length=ATTRIBUTE_KEY_MAX)
    name: str = Field(max_length=ATTRIBUTE_NAME_MAX)
    data_type: AttributeDataType
    options: list[OptionData]
