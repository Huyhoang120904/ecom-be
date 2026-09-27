"""Contract: a shop's products, and their attribute values.

Marked ``db`` because tenancy, the leaf rule and the value checks are queries and
constraints. Built on the seeded catalog.
"""

from __future__ import annotations

import pytest
from catalog_helpers import PRODUCTS, create_product, new_id
from sqlalchemy import text

pytestmark = [pytest.mark.anyio, pytest.mark.db]


class TestCreate:
    async def test_a_product_starts_as_a_draft_owned_by_the_callers_shop(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        assert product["status"] == "draft"
        assert product["category_id"] == seeded.categories["ao-thun"]
        assert product["attributes"] == []
        assert product["variants"] == []
        assert product["images"] == []

    async def test_the_shop_comes_from_the_token_not_the_body(
        self, db_async_client, db_session, owner, seeded
    ):
        response = await db_async_client.post(
            PRODUCTS,
            json={
                "category_id": seeded.categories["ao-thun"],
                "name": "Áo Polo Nike",
                "shop_id": new_id(),
            },
            headers=owner.headers,
        )

        assert response.status_code == 422

    async def test_created_by_and_updated_by_record_who_acted(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        row = (
            await db_session.execute(
                text(
                    "SELECT p.shop_id, u.email, "
                    "p.created_by_user_id = p.updated_by_user_id "
                    "FROM products p JOIN users u ON u.id = p.created_by_user_id "
                    "WHERE p.id = :id"
                ),
                {"id": product["id"]},
            )
        ).one()
        assert str(row[0]) == str(owner.shop_id)
        assert row[1] == owner.email
        assert row[2] is True

    async def test_status_cannot_be_sent(self, db_async_client, owner, seeded):
        response = await db_async_client.post(
            PRODUCTS,
            json={
                "category_id": seeded.categories["ao-thun"],
                "name": "Áo Polo Nike",
                "status": "active",
            },
            headers=owner.headers,
        )

        assert response.status_code == 422

    async def test_a_product_must_sit_in_a_leaf_category(
        self, db_async_client, owner, seeded
    ):
        response = await db_async_client.post(
            PRODUCTS,
            json={"category_id": seeded.categories["thoi-trang"], "name": "Áo"},
            headers=owner.headers,
        )

        assert response.status_code == 422
        assert response.json()["error"] == "category_not_leaf"

    async def test_an_unknown_category_or_brand_is_a_404(
        self, db_async_client, owner, seeded
    ):
        missing_category = await db_async_client.post(
            PRODUCTS,
            json={"category_id": new_id(), "name": "Áo"},
            headers=owner.headers,
        )
        missing_brand = await db_async_client.post(
            PRODUCTS,
            json={
                "category_id": seeded.categories["ao-thun"],
                "name": "Áo",
                "brand_id": new_id(),
            },
            headers=owner.headers,
        )

        assert missing_category.json()["error"] == "category_not_found"
        assert missing_brand.json()["error"] == "brand_not_found"

    async def test_a_brand_can_be_attached(self, db_async_client, owner, seeded):
        product = await create_product(
            db_async_client,
            owner.headers,
            seeded.categories["ao-thun"],
            brand_id=seeded.brands["nike"],
        )

        assert product["brand_id"] == seeded.brands["nike"]


class TestPermissions:
    async def test_a_viewer_can_read_but_not_write(
        self, db_async_client, owner, demote, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        await demote(owner, "viewer")

        read = await db_async_client.get(
            f"{PRODUCTS}/{product['id']}", headers=owner.headers
        )
        write = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}", json={"name": "New"}, headers=owner.headers
        )
        create = await db_async_client.post(
            PRODUCTS,
            json={"category_id": seeded.categories["ao-thun"], "name": "Áo"},
            headers=owner.headers,
        )

        assert read.status_code == 200
        assert write.status_code == 403
        assert create.status_code == 403

    async def test_a_manager_can_write(self, db_async_client, owner, demote, seeded):
        await demote(owner, "manager")

        response = await db_async_client.post(
            PRODUCTS,
            json={"category_id": seeded.categories["ao-thun"], "name": "Áo"},
            headers=owner.headers,
        )

        assert response.status_code == 201

    async def test_authentication_is_required(self, db_async_client):
        assert (await db_async_client.get(PRODUCTS)).status_code == 401


class TestTenancy:
    async def test_a_product_of_another_shop_is_a_404_everywhere(
        self, db_async_client, register_seller, seeded
    ):
        alice = await register_seller("alice@example.com", "Alice Shop")
        bob = await register_seller("bob@example.com", "Bob Shop")
        product = await create_product(
            db_async_client, alice.headers, seeded.categories["ao-thun"]
        )
        url = f"{PRODUCTS}/{product['id']}"

        for method, kwargs in (
            ("get", {}),
            ("patch", {"json": {"name": "Hijack"}}),
            ("delete", {}),
            ("post", {"url": f"{url}/publish"}),
        ):
            target = kwargs.pop("url", url)
            response = await getattr(db_async_client, method)(
                target, headers=bob.headers, **kwargs
            )
            assert response.status_code == 404, method
            assert response.json()["error"] == "product_not_found"

    async def test_lists_show_only_the_callers_products(
        self, db_async_client, register_seller, seeded
    ):
        alice = await register_seller("alice@example.com", "Alice Shop")
        bob = await register_seller("bob@example.com", "Bob Shop")
        await create_product(
            db_async_client, alice.headers, seeded.categories["ao-thun"], "Alice's"
        )
        await create_product(
            db_async_client, bob.headers, seeded.categories["ao-thun"], "Bob's"
        )

        alice_list = await db_async_client.get(PRODUCTS, headers=alice.headers)

        assert [p["name"] for p in alice_list.json()["data"]["items"]] == ["Alice's"]


class TestListEditDelete:
    async def test_pagination_and_status_filter(self, db_async_client, owner, seeded):
        for index in range(3):
            await create_product(
                db_async_client,
                owner.headers,
                seeded.categories["ao-thun"],
                f"Product {index}",
            )

        page = await db_async_client.get(
            PRODUCTS, params={"page": 2, "page_size": 2}, headers=owner.headers
        )
        drafts = await db_async_client.get(
            PRODUCTS, params={"status": "draft"}, headers=owner.headers
        )
        actives = await db_async_client.get(
            PRODUCTS, params={"status": "active"}, headers=owner.headers
        )

        data = page.json()["data"]
        assert (data["total"], data["page"], data["page_size"]) == (3, 2, 2)
        assert len(data["items"]) == 1
        assert drafts.json()["data"]["total"] == 3
        assert actives.json()["data"]["total"] == 0

    async def test_an_out_of_range_page_size_is_rejected(self, db_async_client, owner):
        response = await db_async_client.get(
            PRODUCTS, params={"page_size": 1000}, headers=owner.headers
        )

        assert response.status_code == 422

    async def test_patch_edits_fields_and_clears_with_null(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client,
            owner.headers,
            seeded.categories["ao-thun"],
            brand_id=seeded.brands["nike"],
            description="Old text",
        )

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"name": "New name", "description": None, "brand_id": None},
            headers=owner.headers,
        )

        data = response.json()["data"]
        assert data["name"] == "New name"
        assert data["description"] is None
        assert data["brand_id"] is None

    async def test_patch_cannot_carry_status_or_category(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        for body in (
            {"status": "active"},
            {"category_id": seeded.categories["laptop"]},
        ):
            response = await db_async_client.patch(
                f"{PRODUCTS}/{product['id']}", json=body, headers=owner.headers
            )
            assert response.status_code == 422, body

    async def test_patch_advances_updated_by_and_updated_at(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"name": "Renamed"},
            headers=owner.headers,
        )

        assert response.json()["data"]["updated_at"] >= product["updated_at"]

    async def test_delete_is_soft_and_hides_the_product(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}", headers=owner.headers
        )

        assert response.status_code == 204
        assert (
            await db_async_client.get(
                f"{PRODUCTS}/{product['id']}", headers=owner.headers
            )
        ).status_code == 404
        listed = await db_async_client.get(PRODUCTS, headers=owner.headers)
        assert listed.json()["data"]["total"] == 0
        kept = await db_session.scalar(
            text("SELECT deleted_at IS NOT NULL FROM products WHERE id = :id"),
            {"id": product["id"]},
        )
        assert kept is True


class TestAttributeValues:
    async def laptop(self, client, owner, seeded, attributes):
        return await client.post(
            PRODUCTS,
            json={
                "category_id": seeded.categories["laptop"],
                "name": "MacBook Pro M4",
                "attributes": attributes,
            },
            headers=owner.headers,
        )

    async def test_values_of_each_type_are_stored_and_read_back(
        self, db_async_client, owner, seeded
    ):
        response = await self.laptop(
            db_async_client,
            owner,
            seeded,
            [
                {"attribute_id": seeded.attributes["cpu"], "value_text": "Apple M4"},
                {
                    "attribute_id": seeded.attributes["screen_size"],
                    "value_number": 14.2,
                },
                seeded.select("color", "Gray"),
            ],
        )

        assert response.status_code == 201, response.text
        by_name = {a["name"]: a for a in response.json()["data"]["attributes"]}
        assert by_name["CPU"]["value_text"] == "Apple M4"
        assert by_name["Screen size (inch)"]["value_number"] == 14.2
        assert by_name["Color"]["option_value"] == "Gray"

    @pytest.mark.parametrize(
        ("attributes", "error"),
        [
            # A text attribute given a number.
            ([{"attribute_id": "cpu", "value_number": 3}], "invalid_attribute_value"),
            # A SELECT attribute given free text.
            (
                [{"attribute_id": "color", "value_text": "Gray"}],
                "invalid_attribute_value",
            ),
            # Blank text.
            ([{"attribute_id": "cpu", "value_text": "   "}], "invalid_attribute_value"),
            # Two fields at once.
            (
                [{"attribute_id": "cpu", "value_text": "M4", "value_number": 1}],
                "invalid_attribute_value",
            ),
            # Not configured for laptops.
            (
                [{"attribute_id": "material", "value_text": "Cotton"}],
                "attribute_not_in_category",
            ),
            # A variation attribute belongs on the variants.
            (
                [{"attribute_id": "ram", "option": ("ram", "16GB")}],
                "attribute_is_variation",
            ),
            # The same attribute twice.
            (
                [
                    {"attribute_id": "cpu", "value_text": "A"},
                    {"attribute_id": "cpu", "value_text": "B"},
                ],
                "duplicate_attribute_value",
            ),
        ],
    )
    async def test_bad_values_are_rejected(
        self, db_async_client, owner, seeded, attributes, error
    ):
        resolved = []
        for entry in attributes:
            entry = dict(entry)
            entry["attribute_id"] = seeded.attributes[entry["attribute_id"]]
            if "option" in entry:
                entry["option_id"] = seeded.options[entry.pop("option")]
            resolved.append(entry)

        response = await self.laptop(db_async_client, owner, seeded, resolved)

        assert response.status_code == 422
        assert response.json()["error"] == error

    async def test_an_option_of_another_attribute_is_rejected(
        self, db_async_client, owner, seeded
    ):
        wrong = {
            "attribute_id": seeded.attributes["color"],
            "option_id": seeded.options[("storage", "512GB")],
        }

        response = await self.laptop(db_async_client, owner, seeded, [wrong])

        assert response.status_code == 422
        assert response.json()["error"] == "invalid_attribute_value"

    async def test_patch_without_attributes_keeps_them(
        self, db_async_client, owner, seeded
    ):
        created = await self.laptop(
            db_async_client,
            owner,
            seeded,
            [{"attribute_id": seeded.attributes["cpu"], "value_text": "Apple M4"}],
        )
        product_id = created.json()["data"]["id"]

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product_id}", json={"name": "Renamed"}, headers=owner.headers
        )

        assert len(response.json()["data"]["attributes"]) == 1

    async def test_patch_with_an_empty_list_clears_them(
        self, db_async_client, owner, seeded
    ):
        created = await self.laptop(
            db_async_client,
            owner,
            seeded,
            [{"attribute_id": seeded.attributes["cpu"], "value_text": "Apple M4"}],
        )
        product_id = created.json()["data"]["id"]

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product_id}", json={"attributes": []}, headers=owner.headers
        )

        assert response.json()["data"]["attributes"] == []

    async def test_patch_with_a_list_replaces_rather_than_merges(
        self, db_async_client, owner, seeded
    ):
        created = await self.laptop(
            db_async_client,
            owner,
            seeded,
            [
                {"attribute_id": seeded.attributes["cpu"], "value_text": "Apple M4"},
                {"attribute_id": seeded.attributes["screen_size"], "value_number": 14},
            ],
        )
        product_id = created.json()["data"]["id"]

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product_id}",
            json={
                "attributes": [
                    {"attribute_id": seeded.attributes["cpu"], "value_text": "M5"}
                ]
            },
            headers=owner.headers,
        )

        values = response.json()["data"]["attributes"]
        assert [(v["name"], v["value_text"]) for v in values] == [("CPU", "M5")]

    async def test_a_null_attributes_field_is_rejected(
        self, db_async_client, owner, seeded
    ):
        created = await self.laptop(db_async_client, owner, seeded, [])

        response = await db_async_client.patch(
            f"{PRODUCTS}/{created.json()['data']['id']}",
            json={"attributes": None},
            headers=owner.headers,
        )

        assert response.status_code == 422
