"""Contract: what the catalog refuses once products depend on it.

Marked ``db`` because "in use" is an existence query across products, values and variant
options. These are the plan's *Catalog invariants* exercised end to end.
"""

from __future__ import annotations

import pytest
from catalog_helpers import PRODUCTS, create_product, new_id, polo

pytestmark = [pytest.mark.anyio, pytest.mark.db]

ADMIN = "/api/v1/admin/catalog"


def attr_url(seeded, category, attribute):
    return (
        f"{ADMIN}/categories/{seeded.categories[category]}"
        f"/attributes/{seeded.attributes[attribute]}"
    )


class TestBrandsAndCategories:
    async def test_a_brand_with_products_cannot_be_deleted(
        self, db_async_client, owner, seeded
    ):
        await create_product(
            db_async_client,
            owner.headers,
            seeded.categories["ao-thun"],
            brand_id=seeded.brands["nike"],
        )

        response = await db_async_client.delete(
            f"{ADMIN}/brands/{seeded.brands['nike']}", headers=owner.headers
        )

        assert response.status_code == 409
        assert response.json()["error"] == "brand_in_use"

    async def test_a_soft_deleted_product_still_holds_its_brand(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client,
            owner.headers,
            seeded.categories["ao-thun"],
            brand_id=seeded.brands["nike"],
        )
        await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}", headers=owner.headers
        )

        response = await db_async_client.delete(
            f"{ADMIN}/brands/{seeded.brands['nike']}", headers=owner.headers
        )

        assert response.status_code == 409

    async def test_a_category_with_products_stays_a_leaf(
        self, db_async_client, owner, seeded
    ):
        await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        ao_thun = seeded.categories["ao-thun"]

        add_child = await db_async_client.post(
            f"{ADMIN}/categories",
            json={"name": "Áo thun cổ tròn", "parent_id": ao_thun},
            headers=owner.headers,
        )
        move_under = await db_async_client.patch(
            f"{ADMIN}/categories/{seeded.categories['laptop']}",
            json={"parent_id": ao_thun},
            headers=owner.headers,
        )
        delete = await db_async_client.delete(
            f"{ADMIN}/categories/{ao_thun}", headers=owner.headers
        )

        for response in (add_child, move_under, delete):
            assert response.status_code == 409
            assert response.json()["error"] == "category_has_products"

    async def test_a_category_that_has_children_takes_no_products(
        self, db_async_client, owner, seeded
    ):
        response = await db_async_client.post(
            PRODUCTS,
            json={"category_id": seeded.categories["may-tinh"], "name": "PC"},
            headers=owner.headers,
        )

        assert response.status_code == 422
        assert response.json()["error"] == "category_not_leaf"


class TestAttributesAndOptions:
    async def test_an_option_a_variant_uses_cannot_be_deleted(
        self, db_async_client, owner, seeded
    ):
        await polo(db_async_client, owner.headers, seeded)

        response = await db_async_client.delete(
            f"{ADMIN}/attributes/{seeded.attributes['color']}"
            f"/options/{seeded.options[('color', 'Black')]}",
            headers=owner.headers,
        )

        assert response.status_code == 409
        assert response.json()["error"] == "option_in_use"

    async def test_an_option_a_product_value_uses_cannot_be_deleted(
        self, db_async_client, owner, seeded
    ):
        await create_product(
            db_async_client,
            owner.headers,
            seeded.categories["laptop"],
            "MacBook",
            attributes=[seeded.select("color", "Gray")],
        )

        response = await db_async_client.delete(
            f"{ADMIN}/attributes/{seeded.attributes['color']}"
            f"/options/{seeded.options[('color', 'Gray')]}",
            headers=owner.headers,
        )

        assert response.status_code == 409
        assert response.json()["error"] == "option_in_use"

    async def test_an_unused_option_can_still_be_deleted(
        self, db_async_client, owner, seeded
    ):
        await polo(db_async_client, owner.headers, seeded)

        response = await db_async_client.delete(
            f"{ADMIN}/attributes/{seeded.attributes['color']}"
            f"/options/{seeded.options[('color', 'Red')]}",
            headers=owner.headers,
        )

        assert response.status_code == 204

    async def test_an_attribute_attached_to_a_category_cannot_be_deleted(
        self, db_async_client, owner, seeded
    ):
        response = await db_async_client.delete(
            f"{ADMIN}/attributes/{seeded.attributes['cpu']}", headers=owner.headers
        )

        assert response.status_code == 409
        assert response.json()["error"] == "attribute_attached"


class TestCategoryConfigurationLocks:
    async def test_is_variation_is_locked_once_variants_use_it(
        self, db_async_client, owner, seeded
    ):
        await polo(db_async_client, owner.headers, seeded)

        response = await db_async_client.put(
            attr_url(seeded, "ao-thun", "color"),
            json={"required": True, "is_variation": False, "position": 1},
            headers=owner.headers,
        )

        assert response.status_code == 409
        assert response.json()["error"] == "variation_flag_locked"

    async def test_is_variation_stays_editable_where_nothing_uses_it(
        self, db_async_client, owner, seeded
    ):
        await polo(db_async_client, owner.headers, seeded)

        # Nothing in phones yet: the flag may change freely there.
        response = await db_async_client.put(
            attr_url(seeded, "dien-thoai", "color"),
            json={"required": False, "is_variation": False, "position": 0},
            headers=owner.headers,
        )

        assert response.status_code == 200
        assert response.json()["data"]["is_variation"] is False

    async def test_detaching_an_attribute_in_use_is_locked(
        self, db_async_client, owner, seeded
    ):
        await polo(db_async_client, owner.headers, seeded)
        await create_product(
            db_async_client,
            owner.headers,
            seeded.categories["laptop"],
            attributes=[{"attribute_id": seeded.attributes["cpu"], "value_text": "M4"}],
        )

        varied = await db_async_client.delete(
            attr_url(seeded, "ao-thun", "size"), headers=owner.headers
        )
        valued = await db_async_client.delete(
            attr_url(seeded, "laptop", "cpu"), headers=owner.headers
        )
        unused = await db_async_client.delete(
            attr_url(seeded, "ao-thun", "material"), headers=owner.headers
        )

        assert varied.status_code == 409
        assert varied.json()["error"] == "attribute_detach_locked"
        assert valued.status_code == 409
        assert unused.status_code == 204

    async def test_an_attribute_may_be_detached_from_a_category_that_does_not_use_it(
        self, db_async_client, owner, seeded
    ):
        await polo(db_async_client, owner.headers, seeded)

        # Phones also have Color, but no phone product uses it.
        response = await db_async_client.delete(
            attr_url(seeded, "dien-thoai", "color"), headers=owner.headers
        )

        assert response.status_code == 204

    async def test_required_and_the_search_flags_stay_editable(
        self, db_async_client, owner, seeded
    ):
        await polo(db_async_client, owner.headers, seeded)

        response = await db_async_client.put(
            attr_url(seeded, "ao-thun", "color"),
            json={
                "required": False,
                "filterable": True,
                "searchable": True,
                "is_variation": True,
                "position": 1,
            },
            headers=owner.headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert (data["required"], data["filterable"], data["searchable"]) == (
            False,
            True,
            True,
        )

    async def test_a_new_attribute_can_be_added_to_a_category_that_has_products(
        self, db_async_client, owner, seeded
    ):
        await polo(db_async_client, owner.headers, seeded)

        response = await db_async_client.put(
            attr_url(seeded, "ao-thun", "chipset"),
            json={"required": True},
            headers=owner.headers,
        )

        assert response.status_code == 200

    async def test_a_variant_of_a_deleted_product_still_locks_the_flag(
        self, db_async_client, owner, seeded
    ):
        """Soft-deleted rows are kept, so they count as use."""

        product = await polo(db_async_client, owner.headers, seeded)
        await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}", headers=owner.headers
        )

        response = await db_async_client.put(
            attr_url(seeded, "ao-thun", "size"),
            json={"required": True, "is_variation": False, "position": 0},
            headers=owner.headers,
        )

        assert response.status_code == 409

    async def test_an_unknown_category_or_attribute_is_a_404(
        self, db_async_client, owner, seeded
    ):
        missing_category = await db_async_client.put(
            f"{ADMIN}/categories/{new_id()}/attributes/{seeded.attributes['cpu']}",
            json={},
            headers=owner.headers,
        )
        missing_attribute = await db_async_client.put(
            f"{ADMIN}/categories/{seeded.categories['laptop']}/attributes/{new_id()}",
            json={},
            headers=owner.headers,
        )

        assert missing_category.status_code == 404
        assert missing_attribute.status_code == 404
