"""Contract: shop settings, the permission guard, and the typed-name deletion.

Marked ``db`` because the guard reads a real membership row, and the deletion's
confirmation is compared against the live name read from the database rather than
anything the client sends.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.repositories import membership_repository

pytestmark = [pytest.mark.anyio, pytest.mark.db]

PASSWORD = "a-perfectly-fine-password"
SHOP_OWNER = {
    "email": "shopowner@example.com",
    "password": PASSWORD,
    "full_name": "Shop Owner",
    "shop_name": "Hoang Goods",
}


async def owner_headers(client: AsyncClient) -> dict[str, str]:
    await client.post("/api/v1/auth/register", json=SHOP_OWNER)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": SHOP_OWNER["email"], "password": PASSWORD},
    )
    return {"authorization": f"Bearer {login.json()['data']['access_token']}"}


async def current_shop(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.get("/api/v1/auth/me", headers=headers)
    return response.json()["data"]["active_shop"]


class TestPermissionGuard:
    async def test_a_viewer_cannot_update_the_shop(self, db_async_client, db_session):
        """Demoted through the repository, then re-resolved on the next request."""

        headers = await owner_headers(db_async_client)
        shop = await current_shop(db_async_client, headers)
        await membership_repository.set_membership_role_by_key(
            db_session,
            user_email=SHOP_OWNER["email"],
            shop_id=shop["id"],
            role_key="viewer",
        )

        response = await db_async_client.patch(
            "/api/v1/shops/active", json={"name": "Renamed By Viewer"}, headers=headers
        )

        assert response.status_code == 403
        assert response.json() == {
            "error": "forbidden",
            "message": "You do not have permission to do that",
        }

    async def test_the_demotion_takes_effect_without_a_new_token(
        self, db_async_client, db_session
    ):
        """Authority is read per request, so a role change is immediate."""

        headers = await owner_headers(db_async_client)
        shop = await current_shop(db_async_client, headers)
        assert (
            await db_async_client.patch(
                "/api/v1/shops/active",
                json={"description": "Allowed."},
                headers=headers,
            )
        ).status_code == 200

        await membership_repository.set_membership_role_by_key(
            db_session,
            user_email=SHOP_OWNER["email"],
            shop_id=shop["id"],
            role_key="manager",
        )

        # Same token, no re-login: manager lacks shop:update.
        response = await db_async_client.patch(
            "/api/v1/shops/active", json={"description": "Denied."}, headers=headers
        )
        assert response.status_code == 403

    async def test_a_manager_cannot_delete_the_shop(self, db_async_client, db_session):
        headers = await owner_headers(db_async_client)
        shop = await current_shop(db_async_client, headers)
        await membership_repository.set_membership_role_by_key(
            db_session,
            user_email=SHOP_OWNER["email"],
            shop_id=shop["id"],
            role_key="manager",
        )

        response = await db_async_client.request(
            "DELETE",
            "/api/v1/shops/active",
            json={"confirm_shop_name": shop["name"]},
            headers=headers,
        )

        assert response.status_code == 403

    async def test_an_unauthenticated_update_is_a_401(self, db_async_client):
        response = await db_async_client.patch(
            "/api/v1/shops/active", json={"name": "Nobody"}
        )

        assert response.status_code == 401


class TestShopProfileUpdate:
    async def test_renaming_does_not_change_the_slug(self, db_async_client):
        """A settings form must not silently rewrite a public URL."""

        headers = await owner_headers(db_async_client)
        before = await current_shop(db_async_client, headers)

        response = await db_async_client.patch(
            "/api/v1/shops/active",
            json={
                "name": "A Completely Different Name",
                "description": "Lamps and shades.",
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "A Completely Different Name"
        assert data["slug"] == before["slug"] == "hoang-goods"
        assert data["description"] == "Lamps and shades."

    async def test_only_the_supplied_keys_change(self, db_async_client):
        headers = await owner_headers(db_async_client)
        await db_async_client.patch(
            "/api/v1/shops/active",
            json={
                "contact_email": "hello@hoang-goods.example",
                "contact_phone": "+1 (312) 847-1928",
            },
            headers=headers,
        )

        response = await db_async_client.patch(
            "/api/v1/shops/active", json={"description": "Only this."}, headers=headers
        )

        data = response.json()["data"]
        assert data["description"] == "Only this."
        assert data["contact_email"] == "hello@hoang-goods.example"
        assert data["contact_phone"] == "+13128471928"

    async def test_an_explicit_null_clears_an_optional_field(self, db_async_client):
        headers = await owner_headers(db_async_client)
        await db_async_client.patch(
            "/api/v1/shops/active",
            json={"website": "https://shop.example"},
            headers=headers,
        )

        response = await db_async_client.patch(
            "/api/v1/shops/active", json={"website": None}, headers=headers
        )

        assert response.json()["data"]["website"] is None

    async def test_a_website_without_a_scheme_is_a_422(self, db_async_client):
        headers = await owner_headers(db_async_client)

        response = await db_async_client.patch(
            "/api/v1/shops/active", json={"website": "example.com"}, headers=headers
        )

        assert response.status_code == 422
        assert response.json()["error"] == "validation_error"

    async def test_the_response_publishes_no_slug_field_to_set(self, db_async_client):
        """``slug`` is not in the request schema, so sending one is ignored."""

        headers = await owner_headers(db_async_client)
        before = await current_shop(db_async_client, headers)

        response = await db_async_client.patch(
            "/api/v1/shops/active",
            json={"name": "Renamed Again", "slug": "hijacked-slug"},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["data"]["slug"] == before["slug"]

    async def test_a_one_character_name_is_a_422(self, db_async_client):
        headers = await owner_headers(db_async_client)

        response = await db_async_client.patch(
            "/api/v1/shops/active", json={"name": "A"}, headers=headers
        )

        assert response.status_code == 422


class TestShopDeletion:
    async def test_deleting_requires_the_exact_name(self, db_async_client):
        headers = await owner_headers(db_async_client)
        shop = await current_shop(db_async_client, headers)

        wrong = await db_async_client.request(
            "DELETE",
            "/api/v1/shops/active",
            json={"confirm_shop_name": "Not The Name"},
            headers=headers,
        )

        assert wrong.status_code == 422
        assert wrong.json()["error"] == "confirmation_mismatch"
        still_there = await db_async_client.get("/api/v1/auth/me", headers=headers)
        assert still_there.status_code == 200
        assert still_there.json()["data"]["active_shop"]["name"] == shop["name"]

    async def test_the_right_name_deletes_and_ends_the_session(self, db_async_client):
        headers = await owner_headers(db_async_client)
        shop = await current_shop(db_async_client, headers)

        response = await db_async_client.request(
            "DELETE",
            "/api/v1/shops/active",
            json={"confirm_shop_name": shop["name"]},
            headers=headers,
        )

        assert response.status_code == 204
        after = await db_async_client.get("/api/v1/auth/me", headers=headers)
        assert after.status_code == 401
        assert after.json()["error"] == "shop_not_accessible"

    async def test_a_soft_delete_keeps_the_row_and_its_memberships(
        self, db_async_client, db_session
    ):
        """Nothing is purged: hard deletion needs an order cascade policy."""

        headers = await owner_headers(db_async_client)
        shop = await current_shop(db_async_client, headers)
        await db_async_client.request(
            "DELETE",
            "/api/v1/shops/active",
            json={"confirm_shop_name": shop["name"]},
            headers=headers,
        )

        rows = await db_session.execute(
            text("SELECT deleted_at FROM shops WHERE id = :sid"), {"sid": shop["id"]}
        )
        deleted_at = rows.scalar_one()
        assert deleted_at is not None

        live_rows = await db_session.execute(
            text(
                "SELECT count(*) FROM memberships "
                "WHERE shop_id = :sid AND deleted_at IS NULL"
            ),
            {"sid": shop["id"]},
        )
        assert live_rows.scalar_one() == 0, "the memberships are retired with the shop"

    async def test_the_shop_is_confirmed_against_the_database_not_the_request(
        self, db_async_client
    ):
        """A client cannot delete by sending its own idea of the name."""

        headers = await owner_headers(db_async_client)
        shop = await current_shop(db_async_client, headers)

        # A name that differs only by case is still not the name.
        response = await db_async_client.request(
            "DELETE",
            "/api/v1/shops/active",
            json={"confirm_shop_name": shop["name"].upper()},
            headers=headers,
        )

        assert response.status_code == 422

    async def test_deletion_revokes_the_refresh_cookie(self, db_async_client):
        headers = await owner_headers(db_async_client)
        shop = await current_shop(db_async_client, headers)
        await db_async_client.request(
            "DELETE",
            "/api/v1/shops/active",
            json={"confirm_shop_name": shop["name"]},
            headers=headers,
        )

        refresh = await db_async_client.post("/api/v1/auth/refresh")

        assert refresh.status_code == 401

    async def test_a_deleted_shop_can_be_recreated_by_a_new_registration(
        self, db_async_client
    ):
        """The slug is released, because uniqueness is partial on ``deleted_at``."""

        headers = await owner_headers(db_async_client)
        shop = await current_shop(db_async_client, headers)
        await db_async_client.request(
            "DELETE",
            "/api/v1/shops/active",
            json={"confirm_shop_name": shop["name"]},
            headers=headers,
        )

        response = await db_async_client.post(
            "/api/v1/auth/register",
            json={**SHOP_OWNER, "email": "another@example.com"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["active_shop"]["slug"] == "hoang-goods"
