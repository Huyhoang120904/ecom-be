"""Shapes no single flow owns.

``RoleData`` and ``MembershipData`` describe the tenancy between an account and a
shop, which the auth payload embeds and the profile payload embeds too, so neither
flow can own them. The ``Annotated`` aliases are here for the same reason: they
bound a role or permission key wherever it appears.

A payload that *does* have an owning flow lives with that flow even when another
flow embeds it: ``ShopData`` is in ``shop.py`` and ``UserData`` in ``profile.py``,
and ``auth.py`` imports them, because the shape belongs to the flow that defines
what it means.
"""

from typing import Annotated

from pydantic import BaseModel, Field

from app.constants.identity.rbac import (
    PERMISSION_KEY_MAX,
    ROLE_KEY_MAX,
    ROLE_NAME_MAX,
)
from app.schemas.identity.shop import ShopData

# Every string in a response is bounded, including list members, because the
# generated OpenAPI document is the contract and a client generating from it should
# not have to guess a maximum. ``tests/unit/test_openapi_string_limits.py`` walks the
# document and fails on any unbounded string it finds.
PermissionKey = Annotated[str, Field(max_length=PERMISSION_KEY_MAX)]
RoleKey = Annotated[str, Field(max_length=ROLE_KEY_MAX)]
RoleName = Annotated[str, Field(max_length=ROLE_NAME_MAX)]


class RoleData(BaseModel):
    key: RoleKey
    name: RoleName


class MembershipData(BaseModel):
    """One shop the account belongs to, with the role it holds there."""

    shop: ShopData
    role: RoleData
