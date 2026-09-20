"""Authentication payloads: registration, sign-in, rotation, shop switch.

The requests are bounded by ``app.constants.identity.account`` and normalized by
``app.utils.identity``, so a rule has exactly one implementation and the published
document carries a ``maxLength`` for every string.

A partial update is expressed by an optional field defaulting to ``None``;
``model_fields_set`` is what distinguishes "absent, leave it alone" from "explicitly
null, clear it".
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.constants.identity.account import (
    ACCESS_TOKEN_MAX,
    EMAIL_MAX,
    FULL_NAME_MAX,
    PASSWORD_MAX,
    PASSWORD_MIN,
)
from app.constants.identity.shop import SHOP_NAME_MAX, SHOP_NAME_MIN
from app.schemas.identity.common import MembershipData, PermissionKey
from app.schemas.identity.profile import UserData
from app.schemas.identity.shop import ShopData
from app.utils import identity as utils


class RegisterRequest(BaseModel):
    """Create an account and its first shop in one call."""

    email: EmailStr = Field(max_length=EMAIL_MAX)
    password: Annotated[str, Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)]
    full_name: Annotated[str, Field(min_length=1, max_length=FULL_NAME_MAX)]
    shop_name: Annotated[str, Field(min_length=SHOP_NAME_MIN, max_length=SHOP_NAME_MAX)]

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return utils.normalize_email(value)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        utils.validate_password(value)
        return value

    @field_validator("full_name")
    @classmethod
    def _normalize_full_name(cls, value: str) -> str:
        return utils.normalize_name(value, field="full_name")

    @field_validator("shop_name")
    @classmethod
    def _normalize_shop_name(cls, value: str) -> str:
        return utils.normalize_name(value, field="shop_name")


class LoginRequest(BaseModel):
    """Sign in.

    ``password`` is deliberately not length-validated beyond the request bound: a
    wrong password must reach the comparison and fail identically whether it is
    short or long, or the response would disclose the stored password's length.
    """

    email: EmailStr = Field(max_length=EMAIL_MAX)
    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX)]

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return utils.normalize_email(value)


class SwitchShopRequest(BaseModel):
    shop_id: uuid.UUID


class SessionData(BaseModel):
    """A successful sign-in.

    The refresh token is *not* here. It travels only as an httpOnly cookie, so it
    never appears in a response body, a log, or a client's memory.
    """

    access_token: str = Field(max_length=ACCESS_TOKEN_MAX)
    token_type: Literal["bearer"]
    expires_in: int
    user: UserData
    active_shop: ShopData
    memberships: list[MembershipData]
    permissions: list[PermissionKey]
