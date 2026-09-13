"""Identity response schemas and the per-endpoint envelopes.

A concrete envelope subclass per endpoint, never a bare ``BaseResponse[Thing]``: a
bare generic makes OpenAPI name the schema ``BaseResponse_Thing_``, which leaks the
type-variable name into every generated client type.

Note what is *not* here: no ORM model is ever returned, and no password hash, refresh
token, or media object key appears in any response. ``avatar_key`` and
``background_key`` stay server-side; the client receives a derived URL instead, so
the deployment's storage layout never becomes part of the contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ecom_be.api.schemas import BaseResponse
from ecom_be.modules.identity.constants import (
    ACCESS_TOKEN_MAX,
    BIO_MAX,
    EMAIL_MAX,
    FULL_NAME_MAX,
    JOB_TITLE_MAX,
    PHONE_MAX_INPUT,
    SHOP_DESCRIPTION_MAX,
    SHOP_NAME_MAX,
    URL_MAX,
)


class UserData(BaseModel):
    """An account as the seller CMS sees it."""

    id: uuid.UUID
    email: str = Field(max_length=EMAIL_MAX)
    full_name: str = Field(max_length=FULL_NAME_MAX)
    bio: str | None = Field(default=None, max_length=BIO_MAX)
    phone: str | None = Field(default=None, max_length=PHONE_MAX_INPUT)
    job_title: str | None = Field(default=None, max_length=JOB_TITLE_MAX)
    avatar_url: str | None = Field(default=None, max_length=URL_MAX)
    created_at: datetime
    last_login_at: datetime | None = None


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


class RoleData(BaseModel):
    key: str = Field(max_length=64)
    name: str = Field(max_length=80)


class MembershipData(BaseModel):
    """One shop the account belongs to, with the role it holds there."""

    shop: ShopData
    role: RoleData


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
    permissions: list[str]


class MeData(BaseModel):
    """The caller's own identity and the shop the token is scoped to."""

    user: UserData
    active_shop: ShopData
    memberships: list[MembershipData]
    permissions: list[str]


class SessionEnvelope(BaseResponse[SessionData]): ...


class MeEnvelope(BaseResponse[MeData]): ...


class ShopEnvelope(BaseResponse[ShopData]): ...
