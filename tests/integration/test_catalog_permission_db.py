"""Contract: the temporary ``catalog:manage`` permission and who holds it.

Marked ``db`` because the grants are migration data. The route-level check (an owner
can write the catalog, a manager or viewer gets a 403) lives with the brand routes,
the first surface that uses the permission.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.anyio, pytest.mark.db]


async def _holders(db_session) -> set[str]:
    rows = await db_session.execute(
        text(
            "SELECT r.key FROM role_permissions rp "
            "JOIN roles r ON r.id = rp.role_id "
            "JOIN permissions p ON p.id = rp.permission_id "
            "WHERE p.key = 'catalog:manage' AND r.shop_id IS NULL"
        )
    )
    return {row[0] for row in rows}


async def test_only_the_owner_role_holds_catalog_manage(db_session):
    assert await _holders(db_session) == {"owner"}


async def test_the_permission_is_seeded_exactly_once(db_session):
    count = await db_session.scalar(
        text("SELECT count(*) FROM permissions WHERE key = 'catalog:manage'")
    )

    assert count == 1


async def test_the_owner_grant_is_a_single_row(db_session):
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM role_permissions rp "
            "JOIN permissions p ON p.id = rp.permission_id "
            "WHERE p.key = 'catalog:manage'"
        )
    )

    assert count == 1
