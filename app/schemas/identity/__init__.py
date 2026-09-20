"""Identity request and response schemas, one module per flow.

The router layer is split the same way (``app/api/v1/identity/``), so a flow's
requests, its payload, and its routes carry the same name and can be found
together. A ``common`` module holds the shapes and aliases no single flow owns.

This package re-exports every model, so ``from app.schemas.identity import
MeData`` keeps working; ``__all__`` is spelled out because
``no_implicit_reexport`` makes an unlisted re-export a type error.

The envelope these payloads travel in is ``app/schemas/common.py``'s
``BaseResponse``. No payload here declares one: a route applies
``response_model=BaseResponse[MeData]``. Two rules the contract gates enforce:
every string is bounded (``tests/unit/test_openapi_string_limits.py``) and every
``2xx`` body is a ``BaseResponse`` (``tests/unit/test_openapi_envelope.py``).
"""

from app.schemas.identity.auth import (
    LoginRequest,
    RegisterRequest,
    SessionData,
    SwitchShopRequest,
)
from app.schemas.identity.common import (
    MembershipData,
    PermissionKey,
    RoleData,
    RoleKey,
    RoleName,
)
from app.schemas.identity.profile import (
    DeactivateRequest,
    MeData,
    ProfileUpdateRequest,
    UserData,
)
from app.schemas.identity.shop import (
    DeleteShopRequest,
    ShopData,
    ShopUpdateRequest,
)

__all__ = [
    "DeactivateRequest",
    "DeleteShopRequest",
    "LoginRequest",
    "MeData",
    "MembershipData",
    "PermissionKey",
    "ProfileUpdateRequest",
    "RegisterRequest",
    "RoleData",
    "RoleKey",
    "RoleName",
    "SessionData",
    "ShopData",
    "ShopUpdateRequest",
    "SwitchShopRequest",
    "UserData",
]
