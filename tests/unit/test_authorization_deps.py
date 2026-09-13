"""Contract: the authorization guards.

The dependency-override key is the crux. Overriding the *factory's own closure*
would never match the key FastAPI looks up, so these tests override
``get_current_principal``, which is what ``require_permissions`` depends on.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from ecom_be.api.deps import get_current_principal, require_permissions, require_roles
from ecom_be.core.errors import register_exception_handlers
from ecom_be.modules.identity.errors import (
    AccountInactive,
    Forbidden,
    InvalidToken,
    ShopNotAccessible,
)
from ecom_be.modules.identity.principal import Principal

pytestmark = pytest.mark.anyio


def _principal(
    *,
    permissions: frozenset[str] = frozenset({"shop:read"}),
    roles: tuple[str, ...] = ("owner",),
    shop_is_active: bool = True,
) -> Principal:
    return Principal(
        user_id="11111111-1111-4111-8111-111111111111",
        active_shop_id="22222222-2222-4222-8222-222222222222",
        email="seller@example.com",
        roles=roles,
        permissions=permissions,
        shop_is_active=shop_is_active,
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
