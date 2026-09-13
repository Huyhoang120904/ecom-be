"""Contract: account deactivation.

Marked ``db`` because the point is what deactivation does to real rows and real
sessions, and because the one-way behaviour is a property of the stored state rather
than of a service return value.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text

pytestmark = [pytest.mark.anyio, pytest.mark.db]

PASSWORD = "a-perfectly-fine-password"
RETIRING = {
    "email": "retiring@example.com",
    "password": PASSWORD,
    "full_name": "Retiring Seller",
    "shop_name": "Retiring Shop",
}


async def signed_in(client: AsyncClient, payload: dict | None = None) -> dict[str, str]:
    details = payload or RETIRING
    await client.post("/api/v1/auth/register", json=details)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": details["email"], "password": details["password"]},
    )
    return {"authorization": f"Bearer {login.json()['data']['access_token']}"}


async def deactivate(
    client: AsyncClient, headers: dict[str, str], password: str = PASSWORD
):
    return await client.post(
        "/api/v1/auth/deactivate", json={"password": password}, headers=headers
    )


class TestConfirmation:
    async def test_a_wrong_password_changes_nothing(self, db_async_client):
        headers = await signed_in(db_async_client)

        response = await deactivate(db_async_client, headers, "not-the-right-password")

        assert response.status_code == 401
        assert response.json()["error"] == "invalid_credentials"
        # The account still works, so the failed attempt was inert.
        assert (
            await db_async_client.get("/api/v1/auth/me", headers=headers)
        ).status_code == 200

    async def test_a_missing_password_is_a_422(self, db_async_client):
        headers = await signed_in(db_async_client)

        response = await db_async_client.post(
            "/api/v1/auth/deactivate", json={}, headers=headers
        )

        assert response.status_code == 422

    async def test_an_unauthenticated_deactivation_is_a_401(self, db_async_client):
        response = await db_async_client.post(
            "/api/v1/auth/deactivate", json={"password": PASSWORD}
        )

        assert response.status_code == 401

    async def test_the_successful_call_is_a_bodyless_204(self, db_async_client):
        headers = await signed_in(db_async_client)

        response = await deactivate(db_async_client, headers)

        assert response.status_code == 204
        assert response.content == b""


class TestEffects:
    async def test_every_session_ends_not_just_the_current_one(self, db_async_client):
        """A second sign-in stands in for another device."""

        headers = await signed_in(db_async_client)
        second = await db_async_client.post(
            "/api/v1/auth/login",
            json={"email": RETIRING["email"], "password": PASSWORD},
        )
        assert second.status_code == 200

        await deactivate(db_async_client, headers)

        refreshed = await db_async_client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 401
        assert refreshed.json()["error"] == "account_inactive"

    async def test_signing_in_again_is_refused_with_a_specific_code(
        self, db_async_client
    ):
        headers = await signed_in(db_async_client)
        await deactivate(db_async_client, headers)

        response = await db_async_client.post(
            "/api/v1/auth/login",
            json={"email": RETIRING["email"], "password": PASSWORD},
        )

        assert response.status_code == 403
        assert response.json() == {
            "error": "account_deactivated",
            "message": "This account is deactivated",
        }

    async def test_the_email_stays_reserved(self, db_async_client):
        """Deactivation is not deletion: the seller may return."""

        headers = await signed_in(db_async_client)
        await deactivate(db_async_client, headers)

        response = await db_async_client.post(
            "/api/v1/auth/register",
            json={**RETIRING, "shop_name": "A Brand New Shop"},
        )

        assert response.status_code == 409
        assert response.json()["error"] == "email_taken"

    async def test_the_row_survives_with_deactivated_at_set(
        self, db_async_client, db_session
    ):
        headers = await signed_in(db_async_client)
        await deactivate(db_async_client, headers)

        rows = await db_session.execute(
            text("SELECT deleted_at, deactivated_at FROM users WHERE email = :email"),
            {"email": RETIRING["email"]},
        )
        deleted_at, deactivated_at = rows.one()

        assert deactivated_at is not None, "the account is retired"
        assert deleted_at is None, "but not deleted, which is what reserves the email"

    async def test_the_shop_and_membership_are_untouched(
        self, db_async_client, db_session
    ):
        """Only the ability to sign in changes; the seller's data stays."""

        headers = await signed_in(db_async_client)
        await deactivate(db_async_client, headers)

        rows = await db_session.execute(
            text(
                "SELECT count(*) FROM memberships m "
                "JOIN users u ON u.id = m.user_id "
                "WHERE u.email = :email AND m.deleted_at IS NULL"
            ),
            {"email": RETIRING["email"]},
        )

        assert rows.scalar_one() == 1

    async def test_a_deactivated_account_is_locked_out_on_its_next_request(
        self, db_async_client
    ):
        headers = await signed_in(db_async_client)
        await deactivate(db_async_client, headers)

        # The access token is still cryptographically valid; the guard refuses it
        # because the account it names is no longer live.
        response = await db_async_client.get("/api/v1/auth/me", headers=headers)

        assert response.status_code == 401
        assert response.json()["error"] == "account_inactive"

    async def test_the_refresh_cookie_no_longer_works(self, db_async_client):
        headers = await signed_in(db_async_client)
        await deactivate(db_async_client, headers)

        response = await db_async_client.post("/api/v1/auth/refresh")

        assert response.status_code == 401

    async def test_repeat_deactivation_is_refused_rather_than_silent(
        self, db_async_client
    ):
        """The second call has no live principal, so it is a 401, not a second 204."""

        headers = await signed_in(db_async_client)
        assert (await deactivate(db_async_client, headers)).status_code == 204

        again = await deactivate(db_async_client, headers)

        assert again.status_code == 401
