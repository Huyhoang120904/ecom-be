"""Contract: attributes, options, and a category's attribute configuration.

Marked ``db`` because the rules are constraints and existence queries.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.db,
    pytest.mark.usefixtures("empty_catalog"),
]

ATTRIBUTES = "/api/v1/admin/catalog/attributes"
CATEGORIES = "/api/v1/admin/catalog/categories"
READ_CATEGORIES = "/api/v1/catalog/categories"
READ_ATTRIBUTES = "/api/v1/catalog/attributes"


async def make_attribute(client, headers, key, name, data_type):
    response = await client.post(
        ATTRIBUTES,
        json={"key": key, "name": name, "data_type": data_type},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def make_option(client, headers, attribute_id, value):
    response = await client.post(
        f"{ATTRIBUTES}/{attribute_id}/options", json={"value": value}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def make_category(client, headers, name):
    response = await client.post(CATEGORIES, json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def attach(client, headers, category_id, attribute_id, **flags):
    return await client.put(
        f"{CATEGORIES}/{category_id}/attributes/{attribute_id}",
        json=flags,
        headers=headers,
    )


class TestAttributes:
    async def test_create_and_read_back_with_sorted_options(
        self, db_async_client, owner
    ):
        ram = await make_attribute(
            db_async_client, owner.headers, "ram", "RAM", "SELECT"
        )
        for value in ("16GB", "8GB"):
            await make_option(db_async_client, owner.headers, ram["id"], value)

        response = await db_async_client.get(
            f"{READ_ATTRIBUTES}/{ram['id']}", headers=owner.headers
        )

        data = response.json()["data"]
        assert data["data_type"] == "SELECT"
        # Sorted by ``sort_order``, which defaults to insertion order.
        assert [o["value"] for o in data["options"]] == ["16GB", "8GB"]

    async def test_a_duplicate_key_is_a_conflict(self, db_async_client, owner):
        await make_attribute(db_async_client, owner.headers, "color", "Color", "SELECT")

        response = await db_async_client.post(
            ATTRIBUTES,
            json={"key": "color", "name": "Colour", "data_type": "TEXT"},
            headers=owner.headers,
        )

        assert response.status_code == 409
        assert response.json()["error"] == "attribute_exists"

    async def test_key_and_data_type_cannot_be_changed(self, db_async_client, owner):
        attribute = await make_attribute(
            db_async_client, owner.headers, "cpu", "CPU", "TEXT"
        )

        for body in (
            {"name": "CPU", "data_type": "NUMBER"},
            {"name": "CPU", "key": "x1"},
        ):
            response = await db_async_client.patch(
                f"{ATTRIBUTES}/{attribute['id']}", json=body, headers=owner.headers
            )
            assert response.status_code == 422

    async def test_only_the_display_name_changes(self, db_async_client, owner):
        attribute = await make_attribute(
            db_async_client, owner.headers, "cpu", "CPU", "TEXT"
        )

        response = await db_async_client.patch(
            f"{ATTRIBUTES}/{attribute['id']}",
            json={"name": "Processor"},
            headers=owner.headers,
        )

        assert response.json()["data"]["name"] == "Processor"
        assert response.json()["data"]["key"] == "cpu"

    async def test_a_bad_key_is_rejected(self, db_async_client, owner):
        response = await db_async_client.post(
            ATTRIBUTES,
            json={"key": "Bad Key", "name": "X", "data_type": "TEXT"},
            headers=owner.headers,
        )

        assert response.status_code == 422

    async def test_an_attached_attribute_cannot_be_deleted(
        self, db_async_client, owner
    ):
        attribute = await make_attribute(
            db_async_client, owner.headers, "size", "Size", "SELECT"
        )
        category = await make_category(db_async_client, owner.headers, "Áo")
        await attach(db_async_client, owner.headers, category["id"], attribute["id"])

        response = await db_async_client.delete(
            f"{ATTRIBUTES}/{attribute['id']}", headers=owner.headers
        )

        assert response.status_code == 409
        assert response.json()["error"] == "attribute_attached"

    async def test_an_unattached_attribute_can_be_deleted(self, db_async_client, owner):
        attribute = await make_attribute(
            db_async_client, owner.headers, "size", "Size", "SELECT"
        )

        response = await db_async_client.delete(
            f"{ATTRIBUTES}/{attribute['id']}", headers=owner.headers
        )

        assert response.status_code == 204


class TestOptions:
    async def test_only_a_select_attribute_has_options(self, db_async_client, owner):
        text = await make_attribute(
            db_async_client, owner.headers, "cpu", "CPU", "TEXT"
        )

        response = await db_async_client.post(
            f"{ATTRIBUTES}/{text['id']}/options",
            json={"value": "M4"},
            headers=owner.headers,
        )

        assert response.status_code == 422
        assert response.json()["error"] == "options_require_select"

    async def test_a_value_is_unique_within_its_attribute_only(
        self, db_async_client, owner
    ):
        color = await make_attribute(
            db_async_client, owner.headers, "color", "Color", "SELECT"
        )
        size = await make_attribute(
            db_async_client, owner.headers, "size", "Size", "SELECT"
        )
        await make_option(db_async_client, owner.headers, color["id"], "Black")

        clash = await db_async_client.post(
            f"{ATTRIBUTES}/{color['id']}/options",
            json={"value": "Black"},
            headers=owner.headers,
        )
        elsewhere = await db_async_client.post(
            f"{ATTRIBUTES}/{size['id']}/options",
            json={"value": "Black"},
            headers=owner.headers,
        )

        assert clash.status_code == 409
        assert clash.json()["error"] == "option_exists"
        assert elsewhere.status_code == 201

    async def test_rename_and_delete_an_option(self, db_async_client, owner):
        color = await make_attribute(
            db_async_client, owner.headers, "color", "Color", "SELECT"
        )
        option = await make_option(db_async_client, owner.headers, color["id"], "Blak")

        renamed = await db_async_client.patch(
            f"{ATTRIBUTES}/{color['id']}/options/{option['id']}",
            json={"value": "Black"},
            headers=owner.headers,
        )
        deleted = await db_async_client.delete(
            f"{ATTRIBUTES}/{color['id']}/options/{option['id']}",
            headers=owner.headers,
        )

        assert renamed.json()["data"]["value"] == "Black"
        assert deleted.status_code == 204

    async def test_an_option_of_another_attribute_is_not_found(
        self, db_async_client, owner
    ):
        color = await make_attribute(
            db_async_client, owner.headers, "color", "Color", "SELECT"
        )
        size = await make_attribute(
            db_async_client, owner.headers, "size", "Size", "SELECT"
        )
        option = await make_option(db_async_client, owner.headers, color["id"], "Black")

        response = await db_async_client.delete(
            f"{ATTRIBUTES}/{size['id']}/options/{option['id']}", headers=owner.headers
        )

        assert response.status_code == 404
        assert response.json()["error"] == "option_not_found"


class TestCategoryConfiguration:
    async def test_a_new_category_is_configured_by_api_alone(
        self, db_async_client, owner
    ):
        """The point of the design: Dog Food needs no migration."""

        dog_food = await make_category(db_async_client, owner.headers, "Dog Food")
        weight = await make_attribute(
            db_async_client, owner.headers, "weight", "Weight", "NUMBER"
        )
        flavor = await make_attribute(
            db_async_client, owner.headers, "flavor", "Flavor", "SELECT"
        )
        for value in ("Chicken", "Beef", "Salmon"):
            await make_option(db_async_client, owner.headers, flavor["id"], value)
        await attach(
            db_async_client, owner.headers, dog_food["id"], weight["id"], required=True
        )
        await attach(
            db_async_client,
            owner.headers,
            dog_food["id"],
            flavor["id"],
            required=True,
            position=1,
        )

        response = await db_async_client.get(
            f"{READ_CATEGORIES}/{dog_food['id']}/attributes", headers=owner.headers
        )

        assert response.status_code == 200
        first, second = response.json()["data"]
        assert (first["name"], first["type"], first["required"]) == (
            "Weight",
            "NUMBER",
            True,
        )
        assert first["options"] == []
        assert (second["name"], second["type"], second["required"]) == (
            "Flavor",
            "SELECT",
            True,
        )
        assert [o["value"] for o in second["options"]] == ["Chicken", "Beef", "Salmon"]

    async def test_put_is_idempotent_and_replaces_the_flags(
        self, db_async_client, owner
    ):
        category = await make_category(db_async_client, owner.headers, "Laptop")
        ram = await make_attribute(
            db_async_client, owner.headers, "ram", "RAM", "SELECT"
        )

        first = await attach(
            db_async_client, owner.headers, category["id"], ram["id"], required=True
        )
        second = await attach(
            db_async_client, owner.headers, category["id"], ram["id"], filterable=True
        )

        assert first.status_code == second.status_code == 200
        data = second.json()["data"]
        assert (data["required"], data["filterable"]) == (False, True)
        listed = await db_async_client.get(
            f"{READ_CATEGORIES}/{category['id']}/attributes", headers=owner.headers
        )
        assert len(listed.json()["data"]) == 1

    async def test_only_a_select_attribute_can_be_a_variation(
        self, db_async_client, owner
    ):
        category = await make_category(db_async_client, owner.headers, "Laptop")
        cpu = await make_attribute(db_async_client, owner.headers, "cpu", "CPU", "TEXT")

        response = await attach(
            db_async_client, owner.headers, category["id"], cpu["id"], is_variation=True
        )

        assert response.status_code == 422
        assert response.json()["error"] == "variation_requires_select"

    async def test_detaching_an_unused_attribute_is_allowed(
        self, db_async_client, owner
    ):
        category = await make_category(db_async_client, owner.headers, "Laptop")
        ram = await make_attribute(
            db_async_client, owner.headers, "ram", "RAM", "SELECT"
        )
        await attach(db_async_client, owner.headers, category["id"], ram["id"])

        response = await db_async_client.delete(
            f"{CATEGORIES}/{category['id']}/attributes/{ram['id']}",
            headers=owner.headers,
        )

        assert response.status_code == 204

    async def test_detaching_what_was_never_attached_is_a_404(
        self, db_async_client, owner
    ):
        category = await make_category(db_async_client, owner.headers, "Laptop")
        ram = await make_attribute(
            db_async_client, owner.headers, "ram", "RAM", "SELECT"
        )

        response = await db_async_client.delete(
            f"{CATEGORIES}/{category['id']}/attributes/{ram['id']}",
            headers=owner.headers,
        )

        assert response.status_code == 404
        assert response.json()["error"] == "category_attribute_not_found"

    async def test_configuring_needs_catalog_manage(
        self, db_async_client, owner, demote
    ):
        category = await make_category(db_async_client, owner.headers, "Laptop")
        ram = await make_attribute(
            db_async_client, owner.headers, "ram", "RAM", "SELECT"
        )
        await demote(owner, "viewer")

        response = await attach(
            db_async_client, owner.headers, category["id"], ram["id"]
        )

        assert response.status_code == 403
