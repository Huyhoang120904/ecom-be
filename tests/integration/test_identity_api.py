"""Contract: the identity HTTP surface.

Marked ``db`` as well as anyio, because these exercise the real application whose
request session factory talks to PostgreSQL. The value here is the transport detail
that a service test cannot see: the envelope, the cookie attributes, and the exact
status and error code of each failure.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.anyio, pytest.mark.db]

REGISTER = {
    "email": "api@example.com",
    "password": "a-perfectly-fine-password",
    "full_name": "API Person",
    "shop_name": "API Shop",
}
PASSWORD = REGISTER["password"]


def _cookie_attributes(set_cookie: str) -> dict[str, str]:
    parts = [part.strip() for part in set_cookie.split(";")]
    attributes = {parts[0].split("=")[0]: parts[0].split("=", 1)[1]}
    for part in parts[1:]:
        name, _, value = part.partition("=")
        attributes[name.lower()] = value or "true"
    return attributes


async def _register(client: AsyncClient, payload: dict | None = None):
    return await client.post("/api/v1/auth/register", json=payload or REGISTER)


class TestRegister:
    async def test_returns_an_envelope_and_an_http_only_cookie(self, db_async_client):
        response = await _register(db_async_client)

        assert response.status_code == 201
        body = response.json()
        assert set(body) == {
            "status_code",
            "message",
            "data",
        }, "the body must be a BaseResponse envelope"
        assert body["status_code"] == 201, "the envelope echoes the status code"
        data = body["data"]
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900
        assert data["user"]["email"] == "api@example.com"
        assert data["user"]["phone"] is None
        assert data["active_shop"]["slug"] == "api-shop"
        assert "shop:update" in data["permissions"]

        attributes = _cookie_attributes(response.headers["set-cookie"])
        assert "ecom_refresh" in attributes
        assert attributes["path"] == "/api/v1/auth"
        assert "httponly" in attributes
        assert attributes["samesite"].lower() == "lax"
        assert attributes["max-age"] == "2592000"

    async def test_the_refresh_token_is_absent_from_the_body(self, db_async_client):
        response = await _register(db_async_client)

        body = response.json()["data"]
        assert "refresh_token" not in body
        assert set(body) == {
            "access_token",
            "token_type",
            "expires_in",
            "user",
            "active_shop",
            "memberships",
            "permissions",
        }

    async def test_a_taken_email_is_a_409_without_an_envelope(self, db_async_client):
        await _register(db_async_client)

        response = await _register(db_async_client)

        assert response.status_code == 409
        assert response.json() == {
            "error": "email_taken",
            "message": "That email address is already registered",
        }
        assert "data" not in response.json()

    async def test_a_short_password_is_a_422(self, db_async_client):
        response = await _register(db_async_client, {**REGISTER, "password": "short"})

        assert response.status_code == 422
        assert response.json()["error"] == "validation_error"

    async def test_the_avatar_url_is_null_until_one_is_uploaded(self, db_async_client):
        response = await _register(db_async_client)

        assert response.json()["data"]["user"]["avatar_url"] is None


class TestLoginAndMe:
    async def test_login_then_me_then_logout(self, db_async_client):
        await _register(db_async_client)
        login = await db_async_client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": PASSWORD},
        )
        assert login.status_code == 200
        token = login.json()["data"]["access_token"]

        me = await db_async_client.get(
            "/api/v1/auth/me", headers={"authorization": f"Bearer {token}"}
        )
        assert me.status_code == 200
        assert me.json()["data"]["user"]["email"] == REGISTER["email"]
        assert me.json()["data"]["active_shop"]["name"] == "API Shop"

        logout = await db_async_client.post("/api/v1/auth/logout")
        assert logout.status_code == 204

    async def test_me_without_a_token_is_a_401(self, db_async_client):
        response = await db_async_client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert response.json() == {
            "error": "invalid_token",
            "message": "Authentication required",
        }

    async def test_a_malformed_authorization_header_is_a_401(self, db_async_client):
        response = await db_async_client.get(
            "/api/v1/auth/me", headers={"authorization": "NotBearer xyz"}
        )

        assert response.status_code == 401
        assert response.json()["error"] == "invalid_token"

    async def test_a_wrong_password_and_an_unknown_email_are_identical(
        self, db_async_client
    ):
        await _register(db_async_client)

        wrong = await db_async_client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": "wrong-password-entirely"},
        )
        unknown = await db_async_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong-password-entirely"},
        )

        assert wrong.status_code == unknown.status_code == 401
        assert (
            wrong.json()
            == unknown.json()
            == {
                "error": "invalid_credentials",
                "message": "Email or password is incorrect",
            }
        )


class TestRefresh:
    async def test_refresh_rotates_the_cookie(self, db_async_client):
        await _register(db_async_client)

        first = await db_async_client.post("/api/v1/auth/refresh")
        assert first.status_code == 200
        assert "ecom_refresh=" in first.headers["set-cookie"]

        second = await db_async_client.post("/api/v1/auth/refresh")
        assert second.status_code == 200

    async def test_replaying_an_old_cookie_revokes_the_family(self, db_async_client):
        await _register(db_async_client)
        first = await db_async_client.post("/api/v1/auth/refresh")
        replayed_cookie = first.headers["set-cookie"].split(";")[0]
        await db_async_client.post("/api/v1/auth/refresh")

        replayed = await db_async_client.post(
            "/api/v1/auth/refresh", headers={"cookie": replayed_cookie}
        )

        assert replayed.status_code == 401
        assert replayed.json()["error"] == "invalid_token"

        # The family is gone, so even the live cookie stops working.
        after = await db_async_client.post("/api/v1/auth/refresh")
        assert after.status_code == 401

    async def test_refresh_without_a_cookie_is_a_401(self, db_async_client):
        response = await db_async_client.post("/api/v1/auth/refresh")

        assert response.status_code == 401
        assert response.json()["error"] == "invalid_token"


class TestProfileUpdate:
    async def _headers(self, client: AsyncClient) -> dict[str, str]:
        await _register(client)
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": PASSWORD},
        )
        return {"authorization": f"Bearer {login.json()['data']['access_token']}"}

    async def test_an_omitted_field_is_left_alone(self, db_async_client):
        headers = await self._headers(db_async_client)

        response = await db_async_client.patch(
            "/api/v1/auth/me", json={"bio": "I sell lamps."}, headers=headers
        )

        assert response.status_code == 200
        user = response.json()["data"]["user"]
        assert user["bio"] == "I sell lamps."
        assert user["full_name"] == REGISTER["full_name"]

    async def test_an_explicit_null_clears_a_nullable_field(self, db_async_client):
        headers = await self._headers(db_async_client)
        await db_async_client.patch(
            "/api/v1/auth/me", json={"job_title": "Owner"}, headers=headers
        )

        response = await db_async_client.patch(
            "/api/v1/auth/me", json={"job_title": None}, headers=headers
        )

        assert response.json()["data"]["user"]["job_title"] is None

    async def test_clearing_the_full_name_is_a_422(self, db_async_client):
        headers = await self._headers(db_async_client)

        response = await db_async_client.patch(
            "/api/v1/auth/me", json={"full_name": None}, headers=headers
        )

        assert response.status_code == 422

    async def test_an_over_long_bio_is_a_422(self, db_async_client):
        headers = await self._headers(db_async_client)

        response = await db_async_client.patch(
            "/api/v1/auth/me", json={"bio": "y" * 501}, headers=headers
        )

        assert response.status_code == 422

    async def test_a_phone_is_normalized_on_the_way_in(self, db_async_client):
        headers = await self._headers(db_async_client)

        response = await db_async_client.patch(
            "/api/v1/auth/me", json={"phone": "+1 (312) 847-1928"}, headers=headers
        )

        assert response.json()["data"]["user"]["phone"] == "+13128471928"

    async def test_an_unauthenticated_update_is_a_401(self, db_async_client):
        response = await db_async_client.patch("/api/v1/auth/me", json={"bio": "x"})

        assert response.status_code == 401


class TestDeactivate:
    async def test_requires_the_password_then_locks_the_account(self, db_async_client):
        await _register(db_async_client)
        login = await db_async_client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": PASSWORD},
        )
        headers = {"authorization": f"Bearer {login.json()['data']['access_token']}"}

        wrong = await db_async_client.post(
            "/api/v1/auth/deactivate",
            json={"password": "not-the-password"},
            headers=headers,
        )
        assert wrong.status_code == 401
        assert wrong.json()["error"] == "invalid_credentials"

        ok = await db_async_client.post(
            "/api/v1/auth/deactivate", json={"password": PASSWORD}, headers=headers
        )
        assert ok.status_code == 204

        relogin = await db_async_client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": PASSWORD},
        )
        assert relogin.status_code == 403
        assert relogin.json()["error"] == "account_deactivated"

    async def test_the_email_stays_reserved_after_deactivation(self, db_async_client):
        await _register(db_async_client)
        login = await db_async_client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": PASSWORD},
        )
        await db_async_client.post(
            "/api/v1/auth/deactivate",
            json={"password": PASSWORD},
            headers={"authorization": f"Bearer {login.json()['data']['access_token']}"},
        )

        response = await _register(db_async_client)

        assert response.status_code == 409
        assert response.json()["error"] == "email_taken"
