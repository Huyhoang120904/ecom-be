"""Identity request and response schemas.

Requests: every string is bounded by a constant from ``ecom_be.constants.identity``
and every rule delegates to ``ecom_be.utils.identity``, so each rule has exactly one
implementation and the published OpenAPI document carries a ``maxLength`` for every
string it declares.

Responses: a concrete envelope subclass per endpoint, never a bare
``BaseResponse[Thing]`` -- a bare generic makes OpenAPI name the schema
``BaseResponse_Thing_``, which leaks the type-variable name into every generated
client type. Note what is *not* here: no ORM model is ever returned, and no password
hash, refresh token, or media object key appears in any response. ``avatar_key`` and
``background_key`` stay server-side; the client receives a derived URL instead, so the
deployment's storage layout never becomes part of the contract.

Two rules the contract gates enforce: every string in a response is bounded,
including list members, because a client generating from the document should not have
to guess a maximum (``tests/unit/test_openapi_string_limits.py``); and every ``2xx``
body is an envelope (``tests/unit/test_openapi_envelope.py``).

A partial update is expressed by an optional field defaulting to ``None``.
``model_fields_set`` is what distinguishes "absent, leave it alone" from "explicitly
null, clear it", so the service can honour both.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from ecom_be.constants.identity import (
    ACCESS_TOKEN_MAX,
    BIO_MAX,
    EMAIL_MAX,
    FULL_NAME_MAX,
    JOB_TITLE_MAX,
    PASSWORD_MAX,
    PASSWORD_MIN,
    PERMISSION_KEY_MAX,
    PHONE_MAX_INPUT,
    ROLE_KEY_MAX,
    ROLE_NAME_MAX,
    SHOP_DESCRIPTION_MAX,
    SHOP_NAME_MAX,
    SHOP_NAME_MIN,
    SHOP_WEBSITE_MAX,
    URL_MAX,
)
from ecom_be.schemas.common import BaseResponse
from ecom_be.utils import identity as utils


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


class ProfileUpdateRequest(BaseModel):
    """A partial update of the caller's own profile.

    An omitted key is unchanged; an explicit ``null`` clears a nullable field.
    ``full_name`` may not be cleared, because it is not nullable in the database.
    """

    full_name: Annotated[str, Field(min_length=1, max_length=FULL_NAME_MAX)] | None = (
        None
    )
    bio: Annotated[str | None, Field(max_length=BIO_MAX)] = None
    phone: Annotated[str | None, Field(max_length=PHONE_MAX_INPUT)] = None
    job_title: Annotated[str | None, Field(max_length=JOB_TITLE_MAX)] = None

    @field_validator("full_name")
    @classmethod
    def _normalize_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return utils.normalize_name(value, field="full_name")

    @field_validator("bio")
    @classmethod
    def _normalize_bio(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return utils.normalize_multiline(value, field="bio")

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        return (
            utils.normalize_phone(value, field="phone") if value is not None else None
        )

    @field_validator("job_title")
    @classmethod
    def _normalize_job_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return utils.normalize_name(value, field="job_title")

    @model_validator(mode="after")
    def _full_name_may_not_be_cleared(self) -> ProfileUpdateRequest:
        """An omitted ``full_name`` is fine; an explicit ``null`` is not.

        The field type has to admit ``None`` so that omission can default to it, which
        means the type alone cannot express "nullable in the body but not in the
        database". This checks the one case the type cannot: the key was sent, and
        the client sent null.
        """

        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be cleared")
        return self


class SwitchShopRequest(BaseModel):
    shop_id: uuid.UUID


class DeactivateRequest(BaseModel):
    """Deactivating is one-way, so it is confirmed with the password."""

    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX)]


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
