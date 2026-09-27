"""Contract: a product's variants (SKUs).

Marked ``db`` because uniqueness, tenancy and the cross-variant rules are constraints
and queries.
"""

from __future__ import annotations

import pytest
from catalog_helpers import (
    PRODUCTS,
    add_variant,
    create_product,
    make_variant,
    new_id,
    polo,
)
from sqlalchemy import text

pytestmark = [pytest.mark.anyio, pytest.mark.db]


def variants_url(product_id: str) -> str:
    return f"{PRODUCTS}/{product_id}/variants"


class TestCreate:
    async def test_a_t_shirt_gets_six_color_by_size_variants(
        self, db_async_client, owner, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)

        listed = await db_async_client.get(
            variants_url(product["id"]), headers=owner.headers
        )

        variants = listed.json()["data"]
        assert len(variants) == 6
        prices = {v["sku_code"]: v["price"] for v in variants}
        assert prices["POLO-BLACK-S"] == 300000
        assert prices["POLO-BLACK-L"] == 320000
        first = variants[0]
        assert {o["attribute_name"] for o in first["options"]} == {"Color", "Size"}
        assert first["status"] == "active"
        assert first["stock"] == 10

    async def test_the_same_combination_twice_is_a_conflict(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        options = [seeded.option("color", "Black"), seeded.option("size", "S")]
        await make_variant(
            db_async_client, owner.headers, product["id"], "A", 1, options
        )

        # Same combination, listed in the other order, with a different SKU.
        response = await add_variant(
            db_async_client, owner.headers, product["id"], "B", 1, options[::-1]
        )

        assert response.status_code == 409
        assert response.json()["error"] == "variant_combination_exists"

    async def test_a_sku_code_is_unique_within_a_shop_only(
        self, db_async_client, register_seller, seeded
    ):
        alice = await register_seller("alice@example.com", "Alice Shop")
        bob = await register_seller("bob@example.com", "Bob Shop")
        black_s = [seeded.option("color", "Black"), seeded.option("size", "S")]
        black_m = [seeded.option("color", "Black"), seeded.option("size", "M")]
        a = await create_product(
            db_async_client, alice.headers, seeded.categories["ao-thun"]
        )
        a2 = await create_product(
            db_async_client, alice.headers, seeded.categories["ao-thun"]
        )
        b = await create_product(
            db_async_client, bob.headers, seeded.categories["ao-thun"]
        )
        await make_variant(db_async_client, alice.headers, a["id"], "SKU-1", 1, black_s)

        same_shop = await add_variant(
            db_async_client, alice.headers, a2["id"], "SKU-1", 1, black_m
        )
        other_shop = await add_variant(
            db_async_client, bob.headers, b["id"], "SKU-1", 1, black_s
        )

        assert same_shop.status_code == 409
        assert same_shop.json()["error"] == "sku_exists"
        assert other_shop.status_code == 201

    async def test_only_variation_attributes_of_the_category_are_accepted(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        color = seeded.option("color", "Black")
        cases = {
            # Material is a TEXT attribute, never a variation.
            "not a variation": [
                seeded.option("size", "S"),
                {"attribute_id": seeded.attributes["material"], "option_id": new_id()},
            ],
            # RAM is not configured for T-shirts.
            "not in category": [
                {
                    "attribute_id": seeded.attributes["ram"],
                    "option_id": seeded.options[("ram", "8GB")],
                }
            ],
            # An option that belongs to another attribute.
            "wrong option": [
                {
                    "attribute_id": color["attribute_id"],
                    "option_id": seeded.options[("size", "S")],
                }
            ],
            # The same attribute twice.
            "duplicate": [color, seeded.option("color", "White")],
        }

        for label, options in cases.items():
            response = await add_variant(
                db_async_client, owner.headers, product["id"], f"X-{label}", 1, options
            )
            assert response.status_code == 422, label
            assert response.json()["error"] == "variant_option_invalid", label

    async def test_every_variant_must_use_the_same_variation_attributes(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        await make_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "A",
            1,
            [seeded.option("color", "Black"), seeded.option("size", "S")],
        )

        response = await add_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "B",
            1,
            [seeded.option("color", "White")],
        )

        assert response.status_code == 422
        assert response.json()["error"] == "variation_set_inconsistent"

    async def test_a_product_without_variations_has_exactly_one_optionless_variant(
        self, db_async_client, owner
    ):
        headers = owner.headers
        category = (
            await db_async_client.post(
                "/api/v1/admin/catalog/categories",
                json={"name": "Dog Food"},
                headers=headers,
            )
        ).json()["data"]
        product = await create_product(
            db_async_client, headers, category["id"], "Kibble"
        )

        first = await add_variant(
            db_async_client, headers, product["id"], "KIB-1", 5000
        )
        second = await add_variant(
            db_async_client, headers, product["id"], "KIB-2", 6000
        )

        assert first.status_code == 201
        assert first.json()["data"]["options"] == []
        assert second.status_code == 409
        assert second.json()["error"] == "variant_combination_exists"

    @pytest.mark.parametrize(
        "body",
        [
            {"sku_code": "A", "price": -1},
            {"sku_code": "A", "price": 1, "stock": -1},
            {"sku_code": "", "price": 1},
            {"sku_code": "A", "price": 1, "status": "gone"},
            {"sku_code": "A", "price": 1, "shop_id": "x"},
        ],
    )
    async def test_invalid_bodies_are_rejected(
        self, db_async_client, owner, seeded, body
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await db_async_client.post(
            variants_url(product["id"]), json=body, headers=owner.headers
        )

        assert response.status_code == 422

    async def test_the_variants_shop_is_copied_from_its_product(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        variant = await make_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "A",
            1,
            [seeded.option("color", "Black"), seeded.option("size", "S")],
        )

        shop = await db_session.scalar(
            text("SELECT shop_id FROM product_variants WHERE id = :id"),
            {"id": variant["id"]},
        )

        assert str(shop) == str(owner.shop_id)


class TestPermissionsAndTenancy:
    async def test_a_viewer_can_read_but_not_write_variants(
        self, db_async_client, owner, demote, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)
        await demote(owner, "viewer")

        read = await db_async_client.get(
            variants_url(product["id"]), headers=owner.headers
        )
        write = await add_variant(db_async_client, owner.headers, product["id"], "Z", 1)

        assert read.status_code == 200
        assert write.status_code == 403

    async def test_another_shops_product_has_no_visible_variants(
        self, db_async_client, register_seller, seeded
    ):
        alice = await register_seller("alice@example.com", "Alice Shop")
        bob = await register_seller("bob@example.com", "Bob Shop")
        product = await polo(db_async_client, alice.headers, seeded)
        listed = await db_async_client.get(
            variants_url(product["id"]), headers=alice.headers
        )
        variant_id = listed.json()["data"][0]["id"]

        responses = [
            await db_async_client.get(variants_url(product["id"]), headers=bob.headers),
            await db_async_client.get(
                f"{variants_url(product['id'])}/{variant_id}", headers=bob.headers
            ),
            await db_async_client.patch(
                f"{variants_url(product['id'])}/{variant_id}",
                json={"price": 1},
                headers=bob.headers,
            ),
            await db_async_client.delete(
                f"{variants_url(product['id'])}/{variant_id}", headers=bob.headers
            ),
            await add_variant(db_async_client, bob.headers, product["id"], "HACK", 1),
        ]

        assert {r.status_code for r in responses} == {404}
        assert {r.json()["error"] for r in responses} == {"product_not_found"}


class TestUpdate:
    async def one_variant(self, client, owner, seeded):
        product = await create_product(
            client, owner.headers, seeded.categories["ao-thun"]
        )
        variant = await make_variant(
            client,
            owner.headers,
            product["id"],
            "A",
            1000,
            [seeded.option("color", "Black"), seeded.option("size", "S")],
        )
        return product, variant

    async def test_price_stock_status_and_sku_can_change(
        self, db_async_client, owner, seeded
    ):
        product, variant = await self.one_variant(db_async_client, owner, seeded)

        response = await db_async_client.patch(
            f"{variants_url(product['id'])}/{variant['id']}",
            json={"price": 2500, "stock": 7, "status": "inactive", "sku_code": "A2"},
            headers=owner.headers,
        )

        data = response.json()["data"]
        assert (data["price"], data["stock"], data["status"], data["sku_code"]) == (
            2500,
            7,
            "inactive",
            "A2",
        )

    async def test_stock_is_set_not_added(self, db_async_client, owner, seeded):
        product, variant = await self.one_variant(db_async_client, owner, seeded)
        url = f"{variants_url(product['id'])}/{variant['id']}"

        await db_async_client.patch(url, json={"stock": 10}, headers=owner.headers)
        response = await db_async_client.patch(
            url, json={"stock": 4}, headers=owner.headers
        )

        assert response.json()["data"]["stock"] == 4

    async def test_the_options_cannot_be_edited(self, db_async_client, owner, seeded):
        product, variant = await self.one_variant(db_async_client, owner, seeded)

        response = await db_async_client.patch(
            f"{variants_url(product['id'])}/{variant['id']}",
            json={"options": [seeded.option("color", "White")]},
            headers=owner.headers,
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("body", [{"stock": -1}, {"price": -5}, {"status": "gone"}])
    async def test_invalid_updates_are_rejected(
        self, db_async_client, owner, seeded, body
    ):
        product, variant = await self.one_variant(db_async_client, owner, seeded)

        response = await db_async_client.patch(
            f"{variants_url(product['id'])}/{variant['id']}",
            json=body,
            headers=owner.headers,
        )

        assert response.status_code == 422

    async def test_renaming_onto_a_taken_sku_is_a_conflict(
        self, db_async_client, owner, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)
        listed = await db_async_client.get(
            variants_url(product["id"]), headers=owner.headers
        )
        a, b = listed.json()["data"][:2]

        response = await db_async_client.patch(
            f"{variants_url(product['id'])}/{b['id']}",
            json={"sku_code": a["sku_code"]},
            headers=owner.headers,
        )

        assert response.status_code == 409
        assert response.json()["error"] == "sku_exists"


class TestDelete:
    async def test_delete_is_soft_and_frees_the_sku_and_combination(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        options = [seeded.option("color", "Black"), seeded.option("size", "S")]
        variant = await make_variant(
            db_async_client, owner.headers, product["id"], "A", 1, options
        )

        deleted = await db_async_client.delete(
            f"{variants_url(product['id'])}/{variant['id']}", headers=owner.headers
        )
        again = await add_variant(
            db_async_client, owner.headers, product["id"], "A", 1, options
        )

        assert deleted.status_code == 204
        assert again.status_code == 201
        listed = await db_async_client.get(
            variants_url(product["id"]), headers=owner.headers
        )
        assert len(listed.json()["data"]) == 1
        kept = await db_session.scalar(
            text("SELECT count(*) FROM product_variant_options WHERE variant_id = :id"),
            {"id": variant["id"]},
        )
        assert kept == 2  # the options of a deleted variant are kept

    async def test_a_deleted_product_takes_its_variants_with_it(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)

        await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}", headers=owner.headers
        )

        live = await db_session.scalar(
            text(
                "SELECT count(*) FROM product_variants "
                "WHERE product_id = :id AND deleted_at IS NULL"
            ),
            {"id": product["id"]},
        )
        total = await db_session.scalar(
            text("SELECT count(*) FROM product_variants WHERE product_id = :id"),
            {"id": product["id"]},
        )
        assert (live, total) == (0, 6)
        # The kept rows never leak back out through the API.
        hidden = await db_async_client.get(
            variants_url(product["id"]), headers=owner.headers
        )
        assert hidden.status_code == 404

    async def test_a_missing_variant_is_a_404(self, db_async_client, owner, seeded):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await db_async_client.delete(
            f"{variants_url(product['id'])}/{new_id()}", headers=owner.headers
        )

        assert response.status_code == 404
        assert response.json()["error"] == "variant_not_found"
