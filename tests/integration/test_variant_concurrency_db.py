"""Contract: concurrent writers cannot get past the database's uniqueness.

Marked ``db``. Unlike every other test these use *separate connections that really
commit*, because a shared transaction cannot race with itself. Everything they create is
removed in ``finally`` so the migrated database is left as it was found.

What is proved: the partial unique indexes are the arbiters. Two requests that both
pass the service's read-then-decide checks still cannot both store the same SKU or the
same option combination, and one of them gets the specific ``409``.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.constants.catalog import VariantStatus
from app.errors.catalog import (
    LastActiveVariant,
    ProductInvariantViolated,
    SkuExists,
    VariantCombinationExists,
)
from app.services.product_service import ProductService
from app.services.variant_service import OptionInput, VariantService

pytestmark = [pytest.mark.anyio, pytest.mark.db]


@pytest.fixture
async def world(db_engine):
    """A committed shop and a draft T-shirt product, removed afterwards."""

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    marker = uuid.uuid4().hex[:10]
    async with factory() as session:
        shop = await session.scalar(
            text("INSERT INTO shops (name, slug) VALUES (:name, :slug) RETURNING id"),
            {"name": f"Race {marker}", "slug": f"race-{marker}"},
        )
        user = await session.scalar(
            text(
                "INSERT INTO users (email, password_hash, full_name) "
                "VALUES (:email, 'x', 'Race User') RETURNING id"
            ),
            {"email": f"race-{marker}@example.com"},
        )
        category = await session.scalar(
            text("SELECT id FROM categories WHERE slug = 'ao-thun'")
        )
        product = await session.scalar(
            text(
                "INSERT INTO products (shop_id, category_id, name) "
                "VALUES (:shop, :category, 'Race polo') RETURNING id"
            ),
            {"shop": shop, "category": category},
        )
        rows = await session.execute(
            text(
                "SELECT a.key, o.value, a.id, o.id FROM attribute_options o "
                "JOIN attributes a ON a.id = o.attribute_id "
                "WHERE a.key IN ('color', 'size')"
            )
        )
        options = {(k, v): OptionInput(a, o) for k, v, a, o in rows}
        await session.commit()

    class World:
        pass

    world = World()
    world.factory = factory
    world.shop = shop
    world.user = user
    world.product = product
    world.options = options
    try:
        yield world
    finally:
        async with factory() as session:
            await session.execute(
                text(
                    "DELETE FROM product_variant_options WHERE variant_id IN "
                    "(SELECT id FROM product_variants WHERE product_id = :p)"
                ),
                {"p": product},
            )
            await session.execute(
                text("DELETE FROM product_variants WHERE product_id = :p"),
                {"p": product},
            )
            await session.execute(
                text("DELETE FROM products WHERE id = :p"), {"p": product}
            )
            await session.execute(text("DELETE FROM shops WHERE id = :s"), {"s": shop})
            await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})
            await session.commit()


async def create_variant(world, sku, options):
    """One request: its own session, so it holds its own connection."""

    async with world.factory() as session:
        return await VariantService(session).create_variant(
            shop_id=world.shop,
            product_id=world.product,
            sku_code=sku,
            price=1,
            stock=0,
            status=VariantStatus.ACTIVE,
            options=options,
        )


async def live_variants(world) -> list[str]:
    async with world.factory() as session:
        rows = await session.execute(
            text(
                "SELECT sku_code FROM product_variants "
                "WHERE product_id = :p AND deleted_at IS NULL ORDER BY sku_code"
            ),
            {"p": world.product},
        )
        return [row[0] for row in rows]


def black_s(world):
    return [world.options[("color", "Black")], world.options[("size", "S")]]


async def test_two_requests_for_one_combination_store_exactly_one(world):
    outcomes = await asyncio.gather(
        create_variant(world, "RACE-A", black_s(world)),
        create_variant(world, "RACE-B", black_s(world)[::-1]),
        return_exceptions=True,
    )

    failures = [o for o in outcomes if isinstance(o, Exception)]
    assert len(failures) == 1
    assert isinstance(failures[0], VariantCombinationExists)
    assert len(await live_variants(world)) == 1


async def test_two_requests_for_one_sku_store_exactly_one(world):
    outcomes = await asyncio.gather(
        create_variant(world, "RACE-SKU", black_s(world)),
        create_variant(
            world,
            "RACE-SKU",
            [world.options[("color", "White")], world.options[("size", "M")]],
        ),
        return_exceptions=True,
    )

    failures = [o for o in outcomes if isinstance(o, Exception)]
    assert len(failures) == 1
    assert isinstance(failures[0], SkuExists)
    assert await live_variants(world) == ["RACE-SKU"]


async def test_many_racers_still_leave_one_row_per_combination(world):
    outcomes = await asyncio.gather(
        *(create_variant(world, f"RACE-{n}", black_s(world)) for n in range(6)),
        return_exceptions=True,
    )

    successes = [o for o in outcomes if not isinstance(o, Exception)]
    assert len(successes) == 1
    assert all(
        isinstance(o, VariantCombinationExists)
        for o in outcomes
        if isinstance(o, Exception)
    )
    assert len(await live_variants(world)) == 1


async def test_publish_racing_the_removal_of_the_last_variant_stays_consistent(world):
    """Either publish wins and the delete is refused, or the delete wins and publish is.

    What must never happen is an ``active`` product with no active variant.
    """

    variant = await create_variant(
        world,
        "RACE-LAST",
        [world.options[("color", "Black")], world.options[("size", "S")]],
    )

    async def publish():
        async with world.factory() as session:
            return await ProductService(session).publish(
                shop_id=world.shop, user_id=world.user, product_id=world.product
            )

    async def delete():
        async with world.factory() as session:
            return await VariantService(session).delete_variant(
                shop_id=world.shop,
                product_id=world.product,
                variant_id=variant.variant.id,
            )

    outcomes = await asyncio.gather(publish(), delete(), return_exceptions=True)

    for outcome in outcomes:
        assert not isinstance(outcome, Exception) or isinstance(
            outcome, ProductInvariantViolated | LastActiveVariant
        )
    async with world.factory() as session:
        status = await session.scalar(
            text("SELECT status FROM products WHERE id = :p"), {"p": world.product}
        )
        active = await session.scalar(
            text(
                "SELECT count(*) FROM product_variants "
                "WHERE product_id = :p AND deleted_at IS NULL AND status = 'active'"
            ),
            {"p": world.product},
        )
    assert status != "active" or active >= 1
