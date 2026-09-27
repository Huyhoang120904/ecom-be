"""Contract: the only way a product becomes ``active``, and what it must satisfy.

Marked ``db`` because the rules read the category's configuration, the product's values
and its variants together.
"""

from __future__ import annotations

import pytest
from catalog_helpers import (
    PRODUCTS,
    add_variant,
    create_product,
    make_variant,
    polo,
)

pytestmark = [pytest.mark.anyio, pytest.mark.db]

ADMIN_CATEGORIES = "/api/v1/admin/catalog/categories"


async def publish(client, headers, product_id):
    return await client.post(f"{PRODUCTS}/{product_id}/publish", headers=headers)


async def laptop(client, owner, seeded, *, values=None):
    values = (
        values
        if values is not None
        else [{"attribute_id": seeded.attributes["cpu"], "value_text": "Apple M4"}]
    )
    product = await create_product(
        client,
        owner.headers,
        seeded.categories["laptop"],
        "MacBook Pro M4",
        attributes=values,
    )
    await make_variant(
        client,
        owner.headers,
        product["id"],
        "MBP-16-512",
        45000000,
        [seeded.option("ram", "16GB"), seeded.option("storage", "512GB")],
    )
    return product


class TestPublish:
    async def test_a_complete_product_can_be_published(
        self, db_async_client, owner, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)

        response = await publish(db_async_client, owner.headers, product["id"])

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "active"

    async def test_a_missing_required_attribute_is_named(
        self, db_async_client, owner, seeded
    ):
        product = await laptop(db_async_client, owner, seeded, values=[])

        response = await publish(db_async_client, owner.headers, product["id"])

        assert response.status_code == 422
        body = response.json()
        assert body["error"] == "product_invariant_violated"
        assert body["details"]["missing"] == [
            {
                "attribute_id": seeded.attributes["cpu"],
                "name": "CPU",
                "where": "product",
            }
        ]

    async def test_supplying_the_missing_attribute_lets_it_through(
        self, db_async_client, owner, seeded
    ):
        product = await laptop(db_async_client, owner, seeded, values=[])
        await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={
                "attributes": [
                    {"attribute_id": seeded.attributes["cpu"], "value_text": "M4"}
                ]
            },
            headers=owner.headers,
        )

        response = await publish(db_async_client, owner.headers, product["id"])

        assert response.status_code == 200

    async def test_a_variant_missing_a_required_variation_is_named(
        self, db_async_client, owner, seeded
    ):
        """Size is a required variation; it lives on the variants, not the product."""

        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        # A variant with Color only: the set is consistent, but Size is required.
        await make_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "A",
            1,
            [seeded.option("color", "Black")],
        )

        response = await publish(db_async_client, owner.headers, product["id"])

        assert response.status_code == 422
        assert response.json()["details"]["missing"] == [
            {
                "attribute_id": seeded.attributes["size"],
                "name": "Size",
                "where": "variants",
            }
        ]

    async def test_a_product_needs_an_active_variant(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client,
            owner.headers,
            seeded.categories["laptop"],
            attributes=[{"attribute_id": seeded.attributes["cpu"], "value_text": "M4"}],
        )

        none = await publish(db_async_client, owner.headers, product["id"])
        variant = await make_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "A",
            1,
            [seeded.option("ram", "8GB"), seeded.option("storage", "256GB")],
            status="inactive",
        )
        inactive_only = await publish(db_async_client, owner.headers, product["id"])
        await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}/variants/{variant['id']}",
            json={"status": "active"},
            headers=owner.headers,
        )
        ok = await publish(db_async_client, owner.headers, product["id"])

        assert none.json()["details"]["reasons"] == ["no_active_variant"]
        assert inactive_only.json()["details"]["reasons"] == ["no_active_variant"]
        assert ok.status_code == 200

    async def test_a_variation_attribute_cannot_be_given_as_a_product_value(
        self, db_async_client, owner, seeded
    ):
        response = await db_async_client.post(
            PRODUCTS,
            json={
                "category_id": seeded.categories["ao-thun"],
                "name": "Polo",
                "attributes": [seeded.select("color", "Black")],
            },
            headers=owner.headers,
        )

        assert response.status_code == 422
        assert response.json()["error"] == "attribute_is_variation"

    async def test_a_product_without_variations_publishes_with_one_variant(
        self, db_async_client, owner
    ):
        category = (
            await db_async_client.post(
                ADMIN_CATEGORIES, json={"name": "Dog Food"}, headers=owner.headers
            )
        ).json()["data"]
        product = await create_product(
            db_async_client, owner.headers, category["id"], "Kibble"
        )
        await add_variant(db_async_client, owner.headers, product["id"], "K-1", 5000)

        response = await publish(db_async_client, owner.headers, product["id"])

        assert response.status_code == 200


class TestStatusMoves:
    async def test_the_only_moves_are_publish_and_unpublish(
        self, db_async_client, owner, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)
        pid = product["id"]

        unpublish_draft = await db_async_client.post(
            f"{PRODUCTS}/{pid}/unpublish", headers=owner.headers
        )
        await publish(db_async_client, owner.headers, pid)
        publish_again = await publish(db_async_client, owner.headers, pid)
        unpublished = await db_async_client.post(
            f"{PRODUCTS}/{pid}/unpublish", headers=owner.headers
        )
        republished = await publish(db_async_client, owner.headers, pid)

        assert unpublish_draft.status_code == 409
        assert unpublish_draft.json()["error"] == "invalid_status_transition"
        assert publish_again.status_code == 409
        assert unpublished.json()["data"]["status"] == "inactive"
        assert republished.json()["data"]["status"] == "active"

    async def test_patch_cannot_change_the_status(self, db_async_client, owner, seeded):
        product = await polo(db_async_client, owner.headers, seeded)

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"status": "active"},
            headers=owner.headers,
        )

        assert response.status_code == 422
        after = await db_async_client.get(
            f"{PRODUCTS}/{product['id']}", headers=owner.headers
        )
        assert after.json()["data"]["status"] == "draft"

    async def test_a_viewer_cannot_publish(
        self, db_async_client, owner, demote, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)
        await demote(owner, "viewer")

        response = await publish(db_async_client, owner.headers, product["id"])

        assert response.status_code == 403


class TestActiveProductsStayValid:
    """No mutation of the product itself may push an active product out of bounds."""

    async def active_laptop(self, client, owner, seeded):
        product = await laptop(client, owner, seeded)
        assert (await publish(client, owner.headers, product["id"])).status_code == 200
        return product

    async def test_a_required_value_cannot_be_removed(
        self, db_async_client, owner, seeded
    ):
        product = await self.active_laptop(db_async_client, owner, seeded)

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"attributes": []},
            headers=owner.headers,
        )

        assert response.status_code == 422
        assert response.json()["error"] == "product_invariant_violated"
        after = await db_async_client.get(
            f"{PRODUCTS}/{product['id']}", headers=owner.headers
        )
        assert len(after.json()["data"]["attributes"]) == 1

    async def test_the_last_active_variant_cannot_be_removed_or_deactivated(
        self, db_async_client, owner, seeded
    ):
        product = await self.active_laptop(db_async_client, owner, seeded)
        (variant,) = (
            await db_async_client.get(
                f"{PRODUCTS}/{product['id']}/variants", headers=owner.headers
            )
        ).json()["data"]
        url = f"{PRODUCTS}/{product['id']}/variants/{variant['id']}"

        deactivate = await db_async_client.patch(
            url, json={"status": "inactive"}, headers=owner.headers
        )
        delete = await db_async_client.delete(url, headers=owner.headers)

        assert deactivate.status_code == 409
        assert deactivate.json()["error"] == "last_active_variant"
        assert delete.status_code == 409
        assert delete.json()["error"] == "last_active_variant"

    async def test_a_second_variant_makes_removing_the_first_possible(
        self, db_async_client, owner, seeded
    ):
        product = await self.active_laptop(db_async_client, owner, seeded)
        await make_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "MBP-32-1T",
            60000000,
            [seeded.option("ram", "32GB"), seeded.option("storage", "1TB")],
        )
        first = (
            await db_async_client.get(
                f"{PRODUCTS}/{product['id']}/variants", headers=owner.headers
            )
        ).json()["data"][0]

        response = await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}/variants/{first['id']}", headers=owner.headers
        )

        assert response.status_code == 204

    async def test_a_new_variant_missing_a_required_variation_is_refused(
        self, db_async_client, owner, seeded
    ):
        product = await self.active_laptop(db_async_client, owner, seeded)

        # RAM only: the variation set differs from the existing variant's.
        response = await add_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "MBP-X",
            1,
            [seeded.option("ram", "8GB")],
        )

        assert response.status_code == 422
        assert response.json()["error"] == "variation_set_inconsistent"

    async def test_editing_a_draft_is_not_held_to_the_invariants(
        self, db_async_client, owner, seeded
    ):
        product = await laptop(db_async_client, owner, seeded)

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"attributes": []},
            headers=owner.headers,
        )

        assert response.status_code == 200


class TestStaleProducts:
    """A catalog change may leave an active product stale; it is never unpublished."""

    async def test_a_new_required_attribute_does_not_unpublish_but_blocks_the_next_edit(
        self, db_async_client, owner, seeded
    ):
        product = await laptop(db_async_client, owner, seeded)
        await publish(db_async_client, owner.headers, product["id"])

        # An admin makes Screen size required on laptops.
        await db_async_client.put(
            f"{ADMIN_CATEGORIES}/{seeded.categories['laptop']}"
            f"/attributes/{seeded.attributes['screen_size']}",
            json={"required": True, "position": 3},
            headers=owner.headers,
        )
        still = await db_async_client.get(
            f"{PRODUCTS}/{product['id']}", headers=owner.headers
        )
        edit = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"name": "Renamed"},
            headers=owner.headers,
        )
        fixed = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={
                "attributes": [
                    {"attribute_id": seeded.attributes["cpu"], "value_text": "M4"},
                    {
                        "attribute_id": seeded.attributes["screen_size"],
                        "value_number": 14,
                    },
                ]
            },
            headers=owner.headers,
        )

        assert still.json()["data"]["status"] == "active"
        assert edit.status_code == 422
        assert [m["name"] for m in edit.json()["details"]["missing"]] == [
            "Screen size (inch)"
        ]
        assert fixed.status_code == 200
        assert fixed.json()["data"]["status"] == "active"

    async def test_a_stale_product_must_comply_to_be_published_again(
        self, db_async_client, owner, seeded
    ):
        product = await laptop(db_async_client, owner, seeded)
        await publish(db_async_client, owner.headers, product["id"])
        await db_async_client.put(
            f"{ADMIN_CATEGORIES}/{seeded.categories['laptop']}"
            f"/attributes/{seeded.attributes['screen_size']}",
            json={"required": True, "position": 3},
            headers=owner.headers,
        )
        await db_async_client.post(
            f"{PRODUCTS}/{product['id']}/unpublish", headers=owner.headers
        )

        response = await publish(db_async_client, owner.headers, product["id"])

        assert response.status_code == 422
