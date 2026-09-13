"""Contract: the seeded permission vocabulary and system roles.

Marked ``db`` because the seed is migration data, not code: the only way to know
what the database holds is to ask it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.anyio, pytest.mark.db]

EXPECTED_PERMISSIONS = {
    "dashboard:read",
    "products:read",
    "products:write",
    "orders:read",
    "orders:write",
    "shop:read",
    "shop:update",
    "membership:read",
    "membership:manage",
}

OWNER_ONLY = {"shop:update", "membership:manage"}


async def _permission_keys_for(db_session, role_key: str) -> set[str]:
    rows = await db_session.execute(
        text(
            "SELECT p.key FROM role_permissions rp "
            "JOIN roles r ON r.id = rp.role_id "
            "JOIN permissions p ON p.id = rp.permission_id "
            "WHERE r.key = :role_key AND r.shop_id IS NULL"
        ),
        {"role_key": role_key},
    )
    return {row[0] for row in rows}


async def test_exactly_the_documented_permissions_are_seeded(db_session):
    rows = await db_session.execute(text("SELECT key FROM permissions"))

    assert {row[0] for row in rows} == EXPECTED_PERMISSIONS


async def test_the_three_system_roles_are_seeded_with_no_shop(db_session):
    rows = await db_session.execute(text("SELECT key FROM roles WHERE shop_id IS NULL"))

    assert {row[0] for row in rows} == {"owner", "manager", "viewer"}


async def test_owner_holds_every_permission(db_session):
    assert await _permission_keys_for(db_session, "owner") == EXPECTED_PERMISSIONS


async def test_manager_lacks_the_two_owner_only_permissions(db_session):
    assert await _permission_keys_for(db_session, "manager") == (
        EXPECTED_PERMISSIONS - OWNER_ONLY
    )


async def test_viewer_holds_only_read_permissions(db_session):
    keys = await _permission_keys_for(db_session, "viewer")

    assert keys == {
        "dashboard:read",
        "products:read",
        "orders:read",
        "shop:read",
        "membership:read",
    }
    assert all(key.endswith(":read") for key in keys)


async def test_no_role_holds_a_permission_that_was_not_seeded(db_session):
    rows = await db_session.execute(
        text(
            "SELECT DISTINCT p.key FROM role_permissions rp "
            "JOIN permissions p ON p.id = rp.permission_id"
        )
    )

    assert {row[0] for row in rows} <= EXPECTED_PERMISSIONS
