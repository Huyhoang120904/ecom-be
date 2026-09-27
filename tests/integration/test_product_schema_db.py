"""Contract: what the *database* enforces about products, whatever the service does.

Marked ``db``. Every case below writes a wrong row directly, bypassing the services, and
expects the database itself to refuse it. That is the point of the composite foreign
keys and ``CHECK`` constraints: a bug in a service must not be able to store a row that
contradicts another row.
"""

from __future__ import annotations

import uuid

import pytest
from catalog_helpers import create_product, make_variant
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.anyio, pytest.mark.db]


async def refused(db_session, sql: str, params: dict) -> IntegrityError:
    """Run one statement in a savepoint and return the integrity error it raised."""

    with pytest.raises(IntegrityError) as caught:
        async with db_session.begin_nested():
            await db_session.execute(text(sql), params)
    return caught.value


INSERT_VARIANT = (
    "INSERT INTO product_variants (product_id, shop_id, sku_code, price, stock, "
    "status, option_key) VALUES (:product, :shop, :sku, :price, :stock, :status, :key)"
)


async def a_product(client, owner, seeded, category="ao-thun"):
    return await create_product(client, owner.headers, seeded.categories[category])


class TestVariants:
    async def test_a_variant_cannot_carry_a_different_shop_than_its_product(
        self, db_async_client, db_session, register_seller, seeded
    ):
        alice = await register_seller("alice@example.com", "Alice Shop")
        bob = await register_seller("bob@example.com", "Bob Shop")
        product = await create_product(
            db_async_client, alice.headers, seeded.categories["ao-thun"]
        )

        error = await refused(
            db_session,
            INSERT_VARIANT,
            {
                "product": product["id"],
                "shop": str(bob.shop_id),
                "sku": "X",
                "price": 1,
                "stock": 0,
                "status": "active",
                "key": "",
            },
        )

        assert "variants_product_shop_fk" in str(error)

    @pytest.mark.parametrize(
        ("overrides", "constraint"),
        [
            ({"price": -1}, "variants_price_ck"),
            ({"stock": -1}, "variants_stock_ck"),
            ({"status": "gone"}, "variants_status_ck"),
            ({"sku": "   "}, "variants_sku_ck"),
        ],
    )
    async def test_check_constraints_refuse_bad_values(
        self, db_async_client, db_session, owner, seeded, overrides, constraint
    ):
        product = await a_product(db_async_client, owner, seeded)
        params = {
            "product": product["id"],
            "shop": str(owner.shop_id),
            "sku": "OK",
            "price": 1,
            "stock": 0,
            "status": "active",
            "key": "",
        } | overrides

        error = await refused(db_session, INSERT_VARIANT, params)

        assert constraint in str(error)

    async def test_the_sku_and_the_combination_are_freed_by_a_soft_delete(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await a_product(db_async_client, owner, seeded)
        base = {
            "product": product["id"],
            "shop": str(owner.shop_id),
            "sku": "A",
            "price": 1,
            "stock": 0,
            "status": "active",
            "key": "k",
        }
        await db_session.execute(text(INSERT_VARIANT), base)

        same_sku = await refused(db_session, INSERT_VARIANT, base | {"key": "other"})
        same_combination = await refused(
            db_session, INSERT_VARIANT, base | {"sku": "B"}
        )
        assert "variants_shop_sku_live" in str(same_sku)
        assert "variants_product_combo_live" in str(same_combination)

        await db_session.execute(
            text("UPDATE product_variants SET deleted_at = now() WHERE sku_code = 'A'")
        )
        async with db_session.begin_nested():
            await db_session.execute(text(INSERT_VARIANT), base)  # both keys are free

    async def test_an_option_must_belong_to_its_attribute(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await a_product(db_async_client, owner, seeded)
        variant = await make_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "A",
            1,
            [seeded.option("color", "Black"), seeded.option("size", "S")],
        )

        error = await refused(
            db_session,
            "INSERT INTO product_variant_options (variant_id, attribute_id, option_id) "
            "VALUES (:variant, :attribute, :option)",
            {
                "variant": variant["id"],
                "attribute": seeded.attributes["material"],
                # A Size option filed under Material.
                "option": seeded.options[("size", "M")],
            },
        )

        assert "pvo_option_attribute_fk" in str(error)


class TestAttributeValues:
    INSERT = (
        "INSERT INTO product_attribute_values "
        "(product_id, attribute_id, option_id, value_text, value_number) "
        "VALUES (:product, :attribute, :option, :text, :number)"
    )

    @pytest.mark.parametrize(
        "values",
        [
            {"option": None, "text": None, "number": None},
            {"option": "OPTION", "text": "also text", "number": None},
            {"option": None, "text": "text", "number": 1},
        ],
    )
    async def test_exactly_one_value_column_is_set(
        self, db_async_client, db_session, owner, seeded, values
    ):
        product = await a_product(db_async_client, owner, seeded, "laptop")
        params = {
            "product": product["id"],
            "attribute": seeded.attributes["cpu"],
            "option": None,
            "text": None,
            "number": None,
        } | {
            key: (seeded.options[("color", "Gray")] if value == "OPTION" else value)
            for key, value in values.items()
        }

        error = await refused(db_session, self.INSERT, params)

        assert "pav_exactly_one_value" in str(error)

    async def test_an_option_must_belong_to_its_attribute(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await a_product(db_async_client, owner, seeded, "laptop")

        error = await refused(
            db_session,
            self.INSERT,
            {
                "product": product["id"],
                "attribute": seeded.attributes["color"],
                "option": seeded.options[("storage", "512GB")],
                "text": None,
                "number": None,
            },
        )

        assert "pav_option_attribute_fk" in str(error)


class TestImages:
    INSERT = (
        "INSERT INTO product_images (product_id, variant_id, key, position) "
        "VALUES (:product, :variant, 'k/x.webp', 0)"
    )

    async def test_a_variant_image_must_belong_to_the_same_product(
        self, db_async_client, db_session, owner, seeded
    ):
        one = await a_product(db_async_client, owner, seeded)
        two = await a_product(db_async_client, owner, seeded)
        variant = await make_variant(
            db_async_client,
            owner.headers,
            one["id"],
            "A",
            1,
            [seeded.option("color", "Black"), seeded.option("size", "S")],
        )

        error = await refused(
            db_session, self.INSERT, {"product": two["id"], "variant": variant["id"]}
        )

        assert "product_images_variant_product_fk" in str(error)

    async def test_a_product_level_image_needs_no_variant(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await a_product(db_async_client, owner, seeded)

        async with db_session.begin_nested():
            await db_session.execute(
                text(self.INSERT), {"product": product["id"], "variant": None}
            )

    async def test_a_variant_of_the_same_product_is_accepted(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await a_product(db_async_client, owner, seeded)
        variant = await make_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "A",
            1,
            [seeded.option("color", "Black"), seeded.option("size", "S")],
        )

        async with db_session.begin_nested():
            await db_session.execute(
                text(self.INSERT), {"product": product["id"], "variant": variant["id"]}
            )

    async def test_an_unknown_variant_is_refused(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await a_product(db_async_client, owner, seeded)

        error = await refused(
            db_session,
            self.INSERT,
            {"product": product["id"], "variant": str(uuid.uuid4())},
        )

        assert "product_images_variant_product_fk" in str(error)


class TestProducts:
    async def test_the_status_is_a_closed_set(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await a_product(db_async_client, owner, seeded)

        error = await refused(
            db_session,
            "UPDATE products SET status = 'archived' WHERE id = :id",
            {"id": product["id"]},
        )

        assert "products_status_ck" in str(error)
