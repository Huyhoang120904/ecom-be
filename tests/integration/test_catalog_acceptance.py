"""Acceptance: the scenarios the catalog phase was built to make possible.

Marked ``db``. Each test is one story from ``docs/intent/catalog.md``, driven only
through the HTTP API, so together they are the evidence that the phase works:

* a brand-new category is configured without a migration, and a product in it is
  rejected until its required attributes are given;
* one schema holds a T-shirt (Color x Size, six SKUs, an image per colour) and a laptop
  (RAM x Storage) without either shape being written into a table.
"""

from __future__ import annotations

import pytest
from catalog_helpers import (
    PRODUCTS,
    add_variant,
    create_product,
    make_variant,
    polo,
    upload_image,
)

pytestmark = [pytest.mark.anyio, pytest.mark.db]

ADMIN = "/api/v1/admin/catalog"
READ = "/api/v1/catalog"


class TestNewCategoryNeedsNoMigration:
    async def test_dog_food_is_configured_and_sold_through_the_api_alone(
        self, db_async_client, owner
    ):
        client, headers = db_async_client, owner.headers

        # 1. An admin adds a category and its attributes: no migration, only API calls.
        category = (
            await client.post(
                f"{ADMIN}/categories", json={"name": "Dog Food"}, headers=headers
            )
        ).json()["data"]
        weight = (
            await client.post(
                f"{ADMIN}/attributes",
                json={"key": "weight_kg", "name": "Weight", "data_type": "NUMBER"},
                headers=headers,
            )
        ).json()["data"]
        flavor = (
            await client.post(
                f"{ADMIN}/attributes",
                json={"key": "flavor", "name": "Flavor", "data_type": "SELECT"},
                headers=headers,
            )
        ).json()["data"]
        options = {}
        for value in ("Chicken", "Beef", "Salmon"):
            options[value] = (
                await client.post(
                    f"{ADMIN}/attributes/{flavor['id']}/options",
                    json={"value": value},
                    headers=headers,
                )
            ).json()["data"]["id"]
        for attribute, position in ((weight, 0), (flavor, 1)):
            attached = await client.put(
                f"{ADMIN}/categories/{category['id']}/attributes/{attribute['id']}",
                json={"required": True, "position": position},
                headers=headers,
            )
            assert attached.status_code == 200

        # 2. A frontend asks what a Dog Food product needs and can build its form.
        form = (
            await client.get(
                f"{READ}/categories/{category['id']}/attributes", headers=headers
            )
        ).json()["data"]
        assert [(f["name"], f["type"], f["required"]) for f in form] == [
            ("Weight", "NUMBER", True),
            ("Flavor", "SELECT", True),
        ]
        assert [o["value"] for o in form[1]["options"]] == [
            "Chicken",
            "Beef",
            "Salmon",
        ]

        # 3. A seller lists a product, but cannot publish it until it is complete.
        product = await create_product(client, headers, category["id"], "Royal Canin")
        await add_variant(client, headers, product["id"], "RC-2KG", 250000)
        incomplete = await client.post(
            f"{PRODUCTS}/{product['id']}/publish", headers=headers
        )
        assert incomplete.status_code == 422
        assert {m["name"] for m in incomplete.json()["details"]["missing"]} == {
            "Weight",
            "Flavor",
        }

        completed = await client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={
                "attributes": [
                    {"attribute_id": weight["id"], "value_number": 2},
                    {"attribute_id": flavor["id"], "option_id": options["Chicken"]},
                ]
            },
            headers=headers,
        )
        assert completed.status_code == 200
        published = await client.post(
            f"{PRODUCTS}/{product['id']}/publish", headers=headers
        )
        assert published.status_code == 200
        assert published.json()["data"]["status"] == "active"


class TestOneSchemaManyShapes:
    async def test_a_polo_shirt_has_six_skus_and_an_image_per_colour(
        self, db_async_client, owner, seeded
    ):
        client, headers = db_async_client, owner.headers
        product = await polo(client, headers, seeded)

        variants = (
            await client.get(f"{PRODUCTS}/{product['id']}/variants", headers=headers)
        ).json()["data"]
        assert len(variants) == 6
        assert {v["price"] for v in variants} == {300000, 320000}

        # An image for each colour, on the variant that carries it.
        black = next(v for v in variants if v["sku_code"] == "POLO-BLACK-S")
        white = next(v for v in variants if v["sku_code"] == "POLO-WHITE-S")
        await upload_image(client, headers, product["id"])
        await upload_image(client, headers, product["id"], variant_id=black["id"])
        await upload_image(client, headers, product["id"], variant_id=white["id"])

        published = await client.post(
            f"{PRODUCTS}/{product['id']}/publish", headers=headers
        )
        detail = published.json()["data"]
        assert detail["status"] == "active"
        assert len(detail["images"]) == 1
        by_sku = {v["sku_code"]: v for v in detail["variants"]}
        assert len(by_sku["POLO-BLACK-S"]["images"]) == 1
        assert len(by_sku["POLO-WHITE-S"]["images"]) == 1
        assert by_sku["POLO-BLACK-M"]["images"] == []

    async def test_a_macbook_varies_by_ram_and_storage_on_the_same_tables(
        self, db_async_client, owner, seeded
    ):
        client, headers = db_async_client, owner.headers
        product = await create_product(
            client,
            headers,
            seeded.categories["laptop"],
            "MacBook Pro M4",
            brand_id=seeded.brands["apple"],
            attributes=[
                {"attribute_id": seeded.attributes["cpu"], "value_text": "Apple M4"},
                {
                    "attribute_id": seeded.attributes["screen_size"],
                    "value_number": 14,
                },
            ],
        )
        for ram, storage, sku, price in (
            ("16GB", "512GB", "MBP-16-512", 45000000),
            ("32GB", "1TB", "MBP-32-1T", 60000000),
        ):
            await make_variant(
                client,
                headers,
                product["id"],
                sku,
                price,
                [seeded.option("ram", ram), seeded.option("storage", storage)],
            )

        published = await client.post(
            f"{PRODUCTS}/{product['id']}/publish", headers=headers
        )

        assert published.status_code == 200
        data = published.json()["data"]
        assert data["brand_id"] == seeded.brands["apple"]
        names = {
            option["attribute_name"]
            for variant in data["variants"]
            for option in variant["options"]
        }
        assert names == {"RAM", "Storage"}

    async def test_the_same_polo_cannot_be_published_by_another_shop(
        self, db_async_client, register_seller, seeded
    ):
        alice = await register_seller("alice@example.com", "Alice Shop")
        bob = await register_seller("bob@example.com", "Bob Shop")
        product = await polo(db_async_client, alice.headers, seeded)

        response = await db_async_client.post(
            f"{PRODUCTS}/{product['id']}/publish", headers=bob.headers
        )

        assert response.status_code == 404
