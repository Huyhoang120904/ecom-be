"""Brand requests and payload."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.catalog import BRAND_NAME_MAX, BRAND_NAME_MIN, CATALOG_SLUG_MAX
from app.utils import catalog as utils


class BrandCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=BRAND_NAME_MIN, max_length=BRAND_NAME_MAX)]

    @field_validator("name")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return utils.normalize_text(
            value,
            field_name="brand_name",
            minimum=BRAND_NAME_MIN,
            maximum=BRAND_NAME_MAX,
        )


class BrandUpdateRequest(BrandCreateRequest):
    """Only the name changes; the slug is fixed at creation."""


class BrandData(BaseModel):
    id: uuid.UUID
    name: str = Field(max_length=BRAND_NAME_MAX)
    slug: str = Field(max_length=CATALOG_SLUG_MAX)
