"""Contract: the category tree and its structural rules.

Marked ``db`` because the rules are recursive queries and foreign keys.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.db,
    pytest.mark.usefixtures("empty_catalog"),
]

ADMIN = "/api/v1/admin/catalog/categories"
READ = "/api/v1/catalog/categories"


async def make(client, headers, name, parent_id=None):
    response = await client.post(
        ADMIN, json={"name": name, "parent_id": parent_id}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


class TestTree:
    async def test_the_tree_nests_children_and_marks_leaves(
        self, db_async_client, owner
    ):
        root = await make(db_async_client, owner.headers, "Điện tử")
        computers = await make(db_async_client, owner.headers, "Máy tính", root["id"])
        await make(db_async_client, owner.headers, "Laptop", computers["id"])

        response = await db_async_client.get(READ, headers=owner.headers)

        assert response.status_code == 200
        (top,) = response.json()["data"]
        assert top["name"] == "Điện tử"
        assert top["is_leaf"] is False
        (middle,) = top["children"]
        (leaf,) = middle["children"]
        assert leaf["name"] == "Laptop"
        assert leaf["is_leaf"] is True
        assert leaf["children"] == []

    async def test_get_one_reports_whether_it_is_a_leaf(self, db_async_client, owner):
        root = await make(db_async_client, owner.headers, "Thời trang")
        await make(db_async_client, owner.headers, "Nam", root["id"])

        response = await db_async_client.get(
            f"{READ}/{root['id']}", headers=owner.headers
        )

        assert response.json()["data"]["is_leaf"] is False

    async def test_a_missing_category_is_a_404(self, db_async_client, owner):
        response = await db_async_client.get(
            f"{READ}/00000000-0000-0000-0000-000000000000", headers=owner.headers
        )

        assert response.status_code == 404
        assert response.json()["error"] == "category_not_found"

    async def test_a_missing_parent_is_a_404(self, db_async_client, owner):
        response = await db_async_client.post(
            ADMIN,
            json={
                "name": "Orphan",
                "parent_id": "00000000-0000-0000-0000-000000000000",
            },
            headers=owner.headers,
        )

        assert response.status_code == 404


class TestMoving:
    async def test_a_category_cannot_become_its_own_parent(
        self, db_async_client, owner
    ):
        cat = await make(db_async_client, owner.headers, "Alone")

        response = await db_async_client.patch(
            f"{ADMIN}/{cat['id']}", json={"parent_id": cat["id"]}, headers=owner.headers
        )

        assert response.status_code == 422
        assert response.json()["error"] == "category_cycle"

    async def test_a_category_cannot_move_under_its_descendant(
        self, db_async_client, owner
    ):
        a = await make(db_async_client, owner.headers, "A")
        b = await make(db_async_client, owner.headers, "B", a["id"])
        c = await make(db_async_client, owner.headers, "C", b["id"])

        response = await db_async_client.patch(
            f"{ADMIN}/{a['id']}", json={"parent_id": c["id"]}, headers=owner.headers
        )

        assert response.status_code == 422
        assert response.json()["error"] == "category_cycle"

    async def test_an_explicit_null_moves_to_the_root_but_absent_leaves_it(
        self, db_async_client, owner
    ):
        parent = await make(db_async_client, owner.headers, "Parent")
        child = await make(db_async_client, owner.headers, "Child", parent["id"])

        renamed = await db_async_client.patch(
            f"{ADMIN}/{child['id']}", json={"name": "Renamed"}, headers=owner.headers
        )
        assert renamed.json()["data"]["parent_id"] == parent["id"]

        moved = await db_async_client.patch(
            f"{ADMIN}/{child['id']}", json={"parent_id": None}, headers=owner.headers
        )
        assert moved.json()["data"]["parent_id"] is None

    async def test_the_slug_is_stable_across_a_rename(self, db_async_client, owner):
        cat = await make(db_async_client, owner.headers, "Áo thun")

        renamed = await db_async_client.patch(
            f"{ADMIN}/{cat['id']}", json={"name": "T-Shirts"}, headers=owner.headers
        )

        assert cat["slug"] == "ao-thun"
        assert renamed.json()["data"]["slug"] == "ao-thun"

    async def test_the_tree_depth_is_bounded(self, db_async_client, owner):
        from app.constants.catalog import CATEGORY_MAX_DEPTH

        parent_id = None
        for level in range(CATEGORY_MAX_DEPTH):
            created = await make(db_async_client, owner.headers, f"L{level}", parent_id)
            parent_id = created["id"]

        response = await db_async_client.post(
            ADMIN,
            json={"name": "Too deep", "parent_id": parent_id},
            headers=owner.headers,
        )

        assert response.status_code == 422
        assert response.json()["error"] == "category_too_deep"

    async def test_moving_a_subtree_counts_its_height(self, db_async_client, owner):
        from app.constants.catalog import CATEGORY_MAX_DEPTH

        deep = None
        for level in range(CATEGORY_MAX_DEPTH):
            created = await make(db_async_client, owner.headers, f"D{level}", deep)
            deep = created["id"]
        root = await make(db_async_client, owner.headers, "Other root")
        child = await make(db_async_client, owner.headers, "With kid", root["id"])
        await make(db_async_client, owner.headers, "Kid", child["id"])

        response = await db_async_client.patch(
            f"{ADMIN}/{root['id']}", json={"parent_id": deep}, headers=owner.headers
        )

        assert response.status_code == 422
        assert response.json()["error"] == "category_too_deep"


class TestDeleting:
    async def test_a_category_with_children_cannot_be_deleted(
        self, db_async_client, owner
    ):
        parent = await make(db_async_client, owner.headers, "Parent")
        await make(db_async_client, owner.headers, "Child", parent["id"])

        response = await db_async_client.delete(
            f"{ADMIN}/{parent['id']}", headers=owner.headers
        )

        assert response.status_code == 409
        assert response.json()["error"] == "category_has_children"

    async def test_a_leaf_can_be_deleted(self, db_async_client, owner):
        cat = await make(db_async_client, owner.headers, "Leaf")

        response = await db_async_client.delete(
            f"{ADMIN}/{cat['id']}", headers=owner.headers
        )

        assert response.status_code == 204
        assert (
            await db_async_client.get(f"{READ}/{cat['id']}", headers=owner.headers)
        ).status_code == 404

    async def test_writes_need_catalog_manage(self, db_async_client, owner, demote):
        await demote(owner, "manager")

        response = await db_async_client.post(
            ADMIN, json={"name": "Nope"}, headers=owner.headers
        )

        assert response.status_code == 403
