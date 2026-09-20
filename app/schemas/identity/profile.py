"""The caller's own account: its requests, its payload, and its public shape.

``UserData`` lives here because this flow defines what an account looks like to the
seller CMS; ``auth.py`` imports it for the session payload rather than redefining it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from app.constants.identity.account import (
    BIO_MAX,
    EMAIL_MAX,
    FULL_NAME_MAX,
    JOB_TITLE_MAX,
    PASSWORD_MAX,
    PHONE_MAX_INPUT,
)
from app.constants.identity.media import URL_MAX
from app.schemas.identity.common import MembershipData, PermissionKey
from app.schemas.identity.shop import ShopData
from app.utils import identity as utils


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


class DeactivateRequest(BaseModel):
    """Deactivating is one-way, so it is confirmed with the password."""

    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX)]


class MeData(BaseModel):
    """The caller's own identity and the shop the token is scoped to."""

    user: UserData
    active_shop: ShopData
    memberships: list[MembershipData]
    permissions: list[PermissionKey]


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
