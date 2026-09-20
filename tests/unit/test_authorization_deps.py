"""Contract: the authorization guards.

The dependency-override key is the crux. Overriding the *factory's own closure*
would never match the key FastAPI looks up, so these tests override
``get_current_principal``, which is what ``require_permissions`` depends on.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_current_principal,
    require_audience,
    require_permissions,
    require_platform_admin,
    require_roles,
    require_seller,
    require_seller_permissions,
)
from app.api.principal import Principal
from app.core.errors import register_exception_handlers
from app.errors.identity import (
    AccountInactive,
    Forbidden,
    InvalidToken,
    ShopNotAccessible,
)

pytestmark = pytest.mark.anyio


def _principal(
    *,
    audience: str = "cms",
    permissions: frozenset[str] = frozenset({"shop:read"}),
    roles: tuple[str, ...] = ("owner",),
    shop_is_active: bool = True,
    is_platform_admin: bool = False,
    active_shop_id: str | None = "22222222-2222-4222-8222-222222222222",
) -> Principal:
    return Principal(
        user_id="11111111-1111-4111-8111-111111111111",
        active_shop_id=active_shop_id,
        email="seller@example.com",
        audience=audience,
        roles=roles,
        permissions=permissions,
        shop_is_active=shop_is_active,
        is_platform_admin=is_platform_admin,
    )


def _guarded_app(
    dependency,
    *,
    principal: Principal | None = None,
    error: Exception | None = None,
) -> FastAPI:
    """An app whose principal resolution is replaced by a fixed outcome.

    When neither ``principal`` nor ``error`` is given, the default is a principal
    holding ``shop:read``, so the "this passes" cases do not have to restate it.
    """

    application = FastAPI()
    register_exception_handlers(application)

    @application.get("/guarded")
    # B008 is about calling a function in a default argument. That is exactly how a
    # dependency *factory* is meant to be used, and the alternative (an Annotated
    # string annotation) cannot resolve a closure: with `from __future__ import
    # annotations` the annotation is a string, and `dependency` is not in the module
    # globals for FastAPI to evaluate it.
    async def guarded(
        _: Principal = Depends(dependency),  # noqa: B008
    ) -> dict[str, bool]:
        return {"ok": True}

    resolved = principal if principal is not None else _principal()

    async def fake_principal() -> Principal:
        if error is not None:
            raise error
        return resolved

    application.dependency_overrides[get_current_principal] = fake_principal
    return application


async def _get(application: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        return await client.get("/guarded")


class TestPrincipalShape:
    def test_has_requires_every_key(self):
        principal = _principal(permissions=frozenset({"a", "b"}))

        assert principal.has("a")
        assert principal.has("a", "b")
        assert not principal.has("a", "c")

    def test_has_any_requires_at_least_one(self):
        principal = _principal(permissions=frozenset({"a"}))

        assert principal.has_any("a", "z")
        assert not principal.has_any("y", "z")

    def test_roles_are_tracked_separately_from_permissions(self):
        """A principal may hold a role while the two sets disagree."""

        principal = _principal(roles=("viewer",), permissions=frozenset({"shop:read"}))

        assert principal.has_role("viewer")
        assert not principal.has_role("owner")
        assert principal.has_any_role("owner", "viewer")
        assert not principal.has_any_role("owner", "manager")
        assert not principal.has("viewer"), "a role key is not a permission key"

    def test_the_permission_set_is_immutable(self):
        """A guard that could be mutated by a caller would not be a guard."""

        principal = _principal(permissions=frozenset({"a"}))

        assert isinstance(principal.permissions, frozenset)
        assert not hasattr(principal.permissions, "add")

    def test_platform_admin_bypasses_all_permissions(self):
        admin = _principal(
            audience="admin",
            roles=("sys_admin",),
            permissions=frozenset(),
            is_platform_admin=True,
            active_shop_id=None,
        )

        assert admin.has("random:nonexistent:permission")
        assert admin.has("shop:update", "dashboard:read")
        assert admin.has_any("random:permission")
        assert admin.has_role("sys_admin")
        assert not admin.has_role("owner")


class TestRequirePermissions:
    async def test_a_principal_with_the_key_passes(self):
        response = await _get(_guarded_app(require_permissions("shop:read")))

        assert response.status_code == 200

    async def test_a_principal_missing_the_key_is_forbidden(self):
        response = await _get(
            _guarded_app(require_permissions("shop:update"), principal=_principal())
        )

        assert response.status_code == 403
        assert response.json() == {
            "error": "forbidden",
            "message": "You do not have permission to do that",
        }

    async def test_two_keys_both_matter(self):
        principal = _principal(permissions=frozenset({"a"}))

        response = await _get(
            _guarded_app(require_permissions("a", "b"), principal=principal)
        )

        assert response.status_code == 403

    async def test_no_keys_requires_only_authentication(self):
        response = await _get(
            _guarded_app(
                require_permissions(), principal=_principal(permissions=frozenset())
            )
        )

        assert response.status_code == 200

    async def test_a_missing_token_is_unauthorized_not_forbidden(self):
        response = await _get(
            _guarded_app(require_permissions("shop:read"), error=InvalidToken())
        )

        assert response.status_code == 401
        assert response.json()["error"] == "invalid_token"

    async def test_a_deactivated_account_is_unauthorized(self):
        response = await _get(
            _guarded_app(require_permissions("shop:read"), error=AccountInactive())
        )

        assert response.status_code == 401
        assert response.json()["error"] == "account_inactive"

    async def test_an_inaccessible_shop_is_unauthorized(self):
        response = await _get(
            _guarded_app(require_permissions("shop:read"), error=ShopNotAccessible())
        )

        assert response.status_code == 401
        assert response.json()["error"] == "shop_not_accessible"

    async def test_every_failure_uses_the_stable_error_shape(self):
        for error in (
            InvalidToken(),
            AccountInactive(),
            ShopNotAccessible(),
            Forbidden(),
        ):
            response = await _get(
                _guarded_app(require_permissions("shop:read"), error=error)
            )
            assert set(response.json()) == {"error", "message"}


class TestRequireRoles:
    async def test_a_held_role_passes(self):
        response = await _get(
            _guarded_app(require_roles("owner"), principal=_principal(roles=("owner",)))
        )

        assert response.status_code == 200

    async def test_any_of_the_listed_roles_passes(self):
        response = await _get(
            _guarded_app(
                require_roles("manager", "owner"),
                principal=_principal(roles=("owner",)),
            )
        )

        assert response.status_code == 200

    async def test_an_unheld_role_is_forbidden(self):
        response = await _get(
            _guarded_app(
                require_roles("owner"), principal=_principal(roles=("viewer",))
            )
        )

        assert response.status_code == 403


class TestRequireAudience:
    async def test_matching_audience_passes(self):
        principal = _principal(audience="storefront")
        response = await _get(
            _guarded_app(require_audience("storefront"), principal=principal)
        )

        assert response.status_code == 200

    async def test_one_of_several_allowed_audiences_passes(self):
        principal = _principal(audience="cms")
        response = await _get(
            _guarded_app(require_audience("storefront", "cms"), principal=principal)
        )

        assert response.status_code == 200

    async def test_unmatched_audience_is_forbidden(self):
        principal = _principal(audience="storefront")
        response = await _get(
            _guarded_app(require_audience("cms"), principal=principal)
        )

        assert response.status_code == 403
        assert response.json() == {
            "error": "forbidden",
            "message": "You do not have permission to do that",
        }


class TestRequirePlatformAdmin:
    async def test_platform_admin_passes(self):
        admin = _principal(
            audience="admin",
            roles=("sys_admin",),
            is_platform_admin=True,
            active_shop_id=None,
        )
        response = await _get(_guarded_app(require_platform_admin, principal=admin))

        assert response.status_code == 200

    async def test_non_admin_is_forbidden(self):
        seller = _principal(audience="cms", is_platform_admin=False)
        response = await _get(_guarded_app(require_platform_admin, principal=seller))

        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"

    async def test_admin_with_wrong_audience_is_forbidden(self):
        mismatched = _principal(
            audience="cms",
            roles=("sys_admin",),
            is_platform_admin=True,
        )
        response = await _get(
            _guarded_app(require_platform_admin, principal=mismatched)
        )

        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"


class TestRequireSeller:
    async def test_seller_with_active_shop_passes(self):
        seller = _principal(
            audience="cms",
            active_shop_id="22222222-2222-4222-8222-222222222222",
        )
        response = await _get(_guarded_app(require_seller, principal=seller))

        assert response.status_code == 200

    async def test_storefront_buyer_is_forbidden(self):
        buyer = _principal(
            audience="storefront",
            active_shop_id=None,
        )
        response = await _get(_guarded_app(require_seller, principal=buyer))

        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"

    async def test_seller_without_active_shop_is_forbidden(self):
        broken_seller = _principal(
            audience="cms",
            active_shop_id=None,
        )
        response = await _get(_guarded_app(require_seller, principal=broken_seller))

        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"


class TestRequireSellerPermissions:
    """A shop-scoped route checks the audience *and* the permission, in that order."""

    async def test_a_seller_holding_the_permission_passes(self):
        seller = _principal(
            audience="cms",
            permissions=frozenset({"shop:update"}),
            active_shop_id="22222222-2222-4222-8222-222222222222",
        )
        response = await _get(
            _guarded_app(require_seller_permissions("shop:update"), principal=seller)
        )

        assert response.status_code == 200

    async def test_a_seller_without_the_permission_is_forbidden(self):
        seller = _principal(
            audience="cms",
            permissions=frozenset({"shop:read"}),
            active_shop_id="22222222-2222-4222-8222-222222222222",
        )
        response = await _get(
            _guarded_app(require_seller_permissions("shop:update"), principal=seller)
        )

        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"

    async def test_a_platform_admin_is_refused_despite_every_permission(self):
        """No shop to act in, so the route refuses instead of unpacking a null sid."""

        admin = _principal(
            audience="admin",
            active_shop_id=None,
            roles=("sys_admin",),
            is_platform_admin=True,
        )
        response = await _get(
            _guarded_app(require_seller_permissions("shop:update"), principal=admin)
        )

        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"

    async def test_a_storefront_buyer_is_forbidden(self):
        buyer = _principal(
            audience="storefront",
            active_shop_id=None,
            permissions=frozenset(),
            roles=(),
        )
        response = await _get(
            _guarded_app(require_seller_permissions("shop:update"), principal=buyer)
        )

        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"
