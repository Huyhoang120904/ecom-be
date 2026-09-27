"""Contract: brands, and the ``catalog:manage`` guard they are the first to use.

Marked ``db`` because the guard reads a real membership row and uniqueness is a
database constraint.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.db,
    pytest.mark.usefixtures("empty_catalog"),
]

ADMIN = "/api/v1/admin/catalog/brands"
READ = "/api/v1/catalog/brands"


async def create(client, headers, name="Nike"):
    return await client.post(ADMIN, json={"name": name}, headers=headers)


class TestGuard:
    async def test_an_owner_can_write_the_catalog(self, db_async_client, owner):
        response = await create(db_async_client, owner.headers)

        assert response.status_code == 201
        body = response.json()
        assert body["status_code"] == 201
        assert body["data"]["name"] == "Nike"
        assert body["data"]["slug"] == "nike"

    @pytest.mark.parametrize("role", ["manager", "viewer"])
    async def test_a_manager_or_viewer_cannot_write_the_catalog(
        self, db_async_client, owner, demote, role
    ):
        await demote(owner, role)

        response = await create(db_async_client, owner.headers)

        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"

    async def test_writes_require_authentication(self, db_async_client):
        response = await db_async_client.post(ADMIN, json={"name": "Nike"})

        assert response.status_code == 401

    async def test_a_viewer_can_still_read_the_catalog(
        self, db_async_client, owner, demote
    ):
        await create(db_async_client, owner.headers)
        await demote(owner, "viewer")

        response = await db_async_client.get(READ, headers=owner.headers)

        assert response.status_code == 200
        assert [item["name"] for item in response.json()["data"]] == ["Nike"]

    async def test_reads_require_authentication(self, db_async_client):
        assert (await db_async_client.get(READ)).status_code == 401


class TestBrandRules:
    async def test_a_duplicate_name_is_a_conflict_ignoring_case(
        self, db_async_client, owner
    ):
        await create(db_async_client, owner.headers, "Nike")

        response = await create(db_async_client, owner.headers, "nike")

        assert response.status_code == 409
        assert response.json()["error"] == "brand_exists"

    async def test_two_names_with_one_slug_get_distinct_slugs(
        self, db_async_client, owner
    ):
        first = await create(db_async_client, owner.headers, "Hoàng Gia")
        second = await create(db_async_client, owner.headers, "Hoang Gia!")

        assert first.json()["data"]["slug"] == "hoang-gia"
        assert second.json()["data"]["slug"] == "hoang-gia-2"

    async def test_a_rename_keeps_the_slug(self, db_async_client, owner):
        created = (await create(db_async_client, owner.headers, "Adidas")).json()[
            "data"
        ]

        renamed = await db_async_client.patch(
            f"{ADMIN}/{created['id']}",
            json={"name": "Adidas Originals"},
            headers=owner.headers,
        )

        assert renamed.status_code == 200
        assert renamed.json()["data"]["name"] == "Adidas Originals"
        assert renamed.json()["data"]["slug"] == "adidas"

    async def test_a_rename_onto_an_existing_name_is_a_conflict(
        self, db_async_client, owner
    ):
        await create(db_async_client, owner.headers, "Nike")
        other = (await create(db_async_client, owner.headers, "Puma")).json()["data"]

        response = await db_async_client.patch(
            f"{ADMIN}/{other['id']}", json={"name": "NIKE"}, headers=owner.headers
        )

        assert response.status_code == 409

    async def test_a_missing_brand_is_a_404(self, db_async_client, owner):
        response = await db_async_client.delete(
            f"{ADMIN}/00000000-0000-0000-0000-000000000000", headers=owner.headers
        )

        assert response.status_code == 404
        assert response.json()["error"] == "brand_not_found"

    async def test_an_unused_brand_can_be_deleted(self, db_async_client, owner):
        created = (await create(db_async_client, owner.headers)).json()["data"]

        response = await db_async_client.delete(
            f"{ADMIN}/{created['id']}", headers=owner.headers
        )

        assert response.status_code == 204
        listed = await db_async_client.get(READ, headers=owner.headers)
        assert listed.json()["data"] == []

    async def test_unknown_fields_are_rejected(self, db_async_client, owner):
        response = await db_async_client.post(
            ADMIN, json={"name": "Nike", "slug": "custom"}, headers=owner.headers
        )

        assert response.status_code == 422
