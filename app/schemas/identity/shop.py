"""The active shop: its requests and its public shape.

``ShopData`` lives here because this flow defines what a shop looks like to the
seller CMS; ``auth.py`` and ``profile.py`` import it rather than redefining it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.constants.identity.account import EMAIL_MAX, PHONE_MAX_INPUT
from app.constants.identity.media import URL_MAX
from app.constants.identity.shop import (
    SHOP_DESCRIPTION_MAX,
    SHOP_NAME_MAX,
    SHOP_NAME_MIN,
    SHOP_WEBSITE_MAX,
)
from app.utils import identity as utils


class ShopUpdateRequest(BaseModel):
    """A partial update of the active shop.

    ``slug`` is absent on purpose: it is derived once at creation and a rename must
    not silently rewrite a public URL.
    """

    name: (
        Annotated[str, Field(min_length=SHOP_NAME_MIN, max_length=SHOP_NAME_MAX)] | None
    ) = None
    description: (
        Annotated[str | None, Field(max_length=SHOP_DESCRIPTION_MAX)] | None
    ) = None
    contact_email: Annotated[str | None, Field(max_length=EMAIL_MAX)] = None
    contact_phone: Annotated[str | None, Field(max_length=PHONE_MAX_INPUT)] = None
    website: Annotated[str | None, Field(max_length=SHOP_WEBSITE_MAX)] = None

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return utils.normalize_name(value, field="shop_name")

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return utils.normalize_multiline(value, field="shop_description")

    @field_validator("contact_email")
    @classmethod
    def _normalize_contact_email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return utils.normalize_email(value)

    @field_validator("contact_phone")
    @classmethod
    def _normalize_contact_phone(cls, value: str | None) -> str | None:
        return (
            utils.normalize_phone(value, field="contact_phone")
            if value is not None
            else None
        )

    @field_validator("website")
    @classmethod
    def _check_website(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if not stripped.lower().startswith(("http://", "https://")):
            raise ValueError("website must be an absolute http or https URL")
        return stripped


class DeleteShopRequest(BaseModel):
    """Deleting a shop is one-way, so the shop's own name must be typed."""

    confirm_shop_name: Annotated[
        str, Field(min_length=SHOP_NAME_MIN, max_length=SHOP_NAME_MAX)
    ]


class ShopData(BaseModel):
    """A shop as the seller CMS sees it."""

    id: uuid.UUID
    name: str = Field(max_length=SHOP_NAME_MAX)
    slug: str = Field(max_length=SHOP_NAME_MAX)
    description: str | None = Field(default=None, max_length=SHOP_DESCRIPTION_MAX)
    contact_email: str | None = Field(default=None, max_length=EMAIL_MAX)
    contact_phone: str | None = Field(default=None, max_length=PHONE_MAX_INPUT)
    website: str | None = Field(default=None, max_length=URL_MAX)
    background_url: str | None = Field(default=None, max_length=URL_MAX)
