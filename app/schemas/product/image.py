"""Product image requests and payload."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.constants.identity import URL_MAX

POSITION_MAX = 1000


class ImagePositionRequest(BaseModel):
    """Move an image to a new index in its scope. Nothing else can be changed."""

    model_config = ConfigDict(extra="forbid")

    position: Annotated[int, Field(ge=0, le=POSITION_MAX)]


class ImageData(BaseModel):
    """An image, in the scope it belongs to.

    ``variant_id`` is ``null`` for an image of the product itself. ``position`` is the
    index in that scope, always ``0..n-1``.
    """

    id: uuid.UUID
    variant_id: uuid.UUID | None
    position: int
    url: str = Field(max_length=URL_MAX)
