"""Contract: the seeded sample catalog.

Marked ``db`` because the seed is migration data: the only way to know what the database
holds is to ask it. The tests read through the public API too, so the seed is proven to
be usable, not just present.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.anyio, pytest.mark.db]


async def _category_id(db_session, slug: str):
    return await db_session.scalar(
        text("SELECT id FROM categories WHERE slug = :slug"), {"slug": slug}
    )


async def _config(db_session, slug: str) -> dict[str, tuple[bool, bool]]:
    rows = await db_session.execute(
        text(
            "SELECT a.key, ca.required, ca.is_variation "
            "FROM category_attributes ca "
            "JOIN attributes a ON a.id = ca.attribute_id "
            "JOIN categories c ON c.id = ca.category_id WHERE c.slug = :slug"
        ),
        {"slug": slug},
    )
    return {row[0]: (row[1], row[2]) for row in rows}


async def test_the_category_tree_is_seeded(db_session):
    rows = await db_session.execute(
        text(
            "SELECT c.slug, p.slug FROM categories c "
            "LEFT JOIN categories p ON p.id = c.parent_id"
        )
    )

    tree = {row[0]: row[1] for row in rows}
    assert tree["ao-thun"] == "thoi-trang-nam"
    assert tree["thoi-trang-nam"] == "thoi-trang"
    assert tree["laptop"] == "may-tinh"
    assert tree["may-tinh"] == "dien-tu"
    assert tree["dien-thoai"] == "dien-tu"
    assert tree["thoi-trang"] is None


async def test_t_shirts_vary_by_size_and_color(db_session):
    assert await _config(db_session, "ao-thun") == {
        "size": (True, True),
        "color": (True, True),
        "material": (False, False),
    }


async def test_laptops_vary_by_ram_and_storage(db_session):
    assert await _config(db_session, "laptop") == {
        "ram": (True, True),
        "storage": (True, True),
        "cpu": (True, False),
        "screen_size": (False, False),
        "color": (False, False),
    }


async def test_phones_are_configured(db_session):
    assert await _config(db_session, "dien-thoai") == {
        "color": (True, True),
        "storage": (True, True),
        "ram": (True, False),
        "chipset": (False, False),
    }


async def test_only_select_attributes_are_variations(db_session):
    """A variation must be a SELECT: variants reference an option, not free text."""

    bad = await db_session.scalar(
        text(
            "SELECT count(*) FROM category_attributes ca "
            "JOIN attributes a ON a.id = ca.attribute_id "
            "WHERE ca.is_variation AND a.data_type <> 'SELECT'"
        )
    )

    assert bad == 0


async def test_select_attributes_have_options_and_others_have_none(db_session):
    rows = await db_session.execute(
        text(
            "SELECT a.data_type, count(o.id) FROM attributes a "
            "LEFT JOIN attribute_options o ON o.attribute_id = a.id "
            "GROUP BY a.id, a.data_type"
        )
    )

    for data_type, count in rows:
        assert (count > 0) == (data_type == "SELECT")


async def test_the_seed_is_usable_through_the_api(db_async_client, db_session, owner):
    laptop = await _category_id(db_session, "laptop")

    response = await db_async_client.get(
        f"/api/v1/catalog/categories/{laptop}/attributes", headers=owner.headers
    )

    assert response.status_code == 200
    by_name = {item["name"]: item for item in response.json()["data"]}
    assert by_name["RAM"]["is_variation"] is True
    assert [o["value"] for o in by_name["RAM"]["options"]][:2] == ["4GB", "8GB"]
    assert by_name["CPU"]["options"] == []
