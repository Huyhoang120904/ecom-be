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
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ecom_be.constants.identity import (
    ACCESS_TOKEN_MAX,
    BIO_MAX,
    EMAIL_MAX,
    FULL_NAME_MAX,
    JOB_TITLE_MAX,
    PERMISSION_KEY_MAX,
    PHONE_MAX_INPUT,
    ROLE_KEY_MAX,
    ROLE_NAME_MAX,
    SHOP_DESCRIPTION_MAX,
    SHOP_NAME_MAX,
    URL_MAX,
)
from ecom_be.schemas.common import BaseResponse

# Every string in a response is bounded, including list members, because the
# generated OpenAPI document is the contract and a client generating from it should
# not have to guess a maximum. ``tests/unit/test_openapi_string_limits.py`` walks the
# document and fails on any unbounded string it finds.
PermissionKey = Annotated[str, Field(max_length=PERMISSION_KEY_MAX)]
RoleKey = Annotated[str, Field(max_length=ROLE_KEY_MAX)]
RoleName = Annotated[str, Field(max_length=ROLE_NAME_MAX)]


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
    key: RoleKey
    name: RoleName


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
    permissions: list[PermissionKey]


class MeData(BaseModel):
    """The caller's own identity and the shop the token is scoped to."""

    user: UserData
    active_shop: ShopData
    memberships: list[MembershipData]
    permissions: list[PermissionKey]


class SessionEnvelope(BaseResponse[SessionData]): ...


class MeEnvelope(BaseResponse[MeData]): ...


class ShopEnvelope(BaseResponse[ShopData]): ...
