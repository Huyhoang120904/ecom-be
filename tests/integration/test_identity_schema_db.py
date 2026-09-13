"""Contract: real PostgreSQL behaviour for the identity schema.

Marked ``db`` because every assertion here is about something SQLite cannot
express or would express differently: ``citext``, partial unique indexes, and the
``CHECK`` constraints. Run with ``uv run pytest -q -m db`` against
``docker compose up -d --wait``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.anyio, pytest.mark.db]


async def test_the_citext_extension_and_the_identity_tables_exist(db_session):
    extension = await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'citext'")
    )
    assert extension.scalar_one() == "citext"

    tables = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    names = {row[0] for row in tables}
    assert {
        "users",
        "shops",
        "roles",
        "permissions",
        "memberships",
        "role_permissions",
        "refresh_tokens",
    } <= names


async def test_email_matching_is_case_insensitive(db_session):
    await db_session.execute(
        text(
            "INSERT INTO users (email, password_hash, full_name) "
            "VALUES ('seller@example.com', 'x', 'Seller')"
        )
    )
    matched = await db_session.execute(
        text("SELECT count(*) FROM users WHERE email = 'SELLER@Example.COM'")
    )

    assert matched.scalar_one() == 1


async def test_a_mixed_case_email_is_refused_by_the_check_constraint(db_session):
    with pytest.raises(IntegrityError) as excinfo:
        await db_session.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name) "
                "VALUES ('Mixed@Example.com', 'x', 'Mixed')"
            )
        )

    assert "users_email_lower" in str(excinfo.value)


async def test_a_live_email_collision_is_refused(db_session):
    await db_session.execute(
        text(
            "INSERT INTO users (email, password_hash, full_name) "
            "VALUES ('dupe@example.com', 'x', 'First')"
        )
    )

    with pytest.raises(IntegrityError) as excinfo:
        await db_session.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name) "
                "VALUES ('dupe@example.com', 'x', 'Second')"
            )
        )

    assert "users_email_live" in str(excinfo.value)


async def test_soft_deleting_releases_the_email_for_reuse(db_session):
    """Otherwise retiring an account burns its address permanently."""

    await db_session.execute(
        text(
            "INSERT INTO users (email, password_hash, full_name) "
            "VALUES ('reuse@example.com', 'x', 'First')"
        )
    )
    await db_session.execute(
        text("UPDATE users SET deleted_at = now() WHERE email = 'reuse@example.com'")
    )
    await db_session.execute(
        text(
            "INSERT INTO users (email, password_hash, full_name) "
            "VALUES ('reuse@example.com', 'x', 'Second')"
        )
    )

    rows = await db_session.execute(
        text("SELECT count(*) FROM users WHERE email = 'reuse@example.com'")
    )
    assert rows.scalar_one() == 2, "both rows survive; only one is live"


async def test_soft_deleting_releases_the_slug_for_reuse(db_session):
    """Otherwise retiring a shop burns its public URL permanently."""

    insert = text(
        "INSERT INTO shops (name, slug) VALUES ('Hoang Goods', 'hoang-goods')"
    )
    await db_session.execute(insert)

    # A savepoint, because an IntegrityError aborts the surrounding transaction and
    # every later statement would fail with "current transaction is aborted".
    with pytest.raises(IntegrityError) as excinfo:
        async with db_session.begin_nested():
            await db_session.execute(insert)
    assert "shops_slug_live" in str(excinfo.value)

    await db_session.execute(
        text("UPDATE shops SET deleted_at = now() WHERE slug = 'hoang-goods'")
    )
    await db_session.execute(insert)

    rows = await db_session.execute(
        text("SELECT count(*) FROM shops WHERE slug = 'hoang-goods'")
    )
    assert rows.scalar_one() == 2


async def test_a_system_role_cannot_be_soft_deleted(db_session):
    """The partial unique index keeps the key, so a soft delete is unrecoverable.

    Uses a key the seed does not own, so this asserts the constraint rather than
    the seed's presence.
    """

    await db_session.execute(
        text("INSERT INTO roles (key, name) VALUES ('probe_system', 'Probe System')")
    )

    with pytest.raises(IntegrityError) as excinfo:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE roles SET deleted_at = now() WHERE key = 'probe_system'")
            )

    assert "roles_system_role_not_deleted" in str(excinfo.value)


async def test_a_shop_scoped_role_may_be_soft_deleted(db_session):
    """The restriction applies to system roles only."""

    await db_session.execute(
        text("INSERT INTO shops (name, slug) VALUES ('Scoped Shop', 'scoped-shop')")
    )
    await db_session.execute(
        text(
            "INSERT INTO roles (key, name, shop_id) "
            "SELECT 'custom', 'Custom', id FROM shops WHERE slug = 'scoped-shop'"
        )
    )
    await db_session.execute(
        text("UPDATE roles SET deleted_at = now() WHERE key = 'custom'")
    )

    rows = await db_session.execute(
        text("SELECT deleted_at FROM roles WHERE key = 'custom'")
    )
    assert rows.scalar_one() is not None


async def test_two_system_roles_cannot_share_a_key(db_session):
    """A key the seed does not own, so this tests uniqueness rather than the seed."""

    await db_session.execute(
        text("INSERT INTO roles (key, name) VALUES ('probe_dup', 'Probe One')")
    )

    with pytest.raises(IntegrityError) as excinfo:
        async with db_session.begin_nested():
            await db_session.execute(
                text("INSERT INTO roles (key, name) VALUES ('probe_dup', 'Probe Two')")
            )

    assert "roles_system_key_uniq" in str(excinfo.value)


async def test_a_whitespace_only_full_name_is_refused(db_session):
    with pytest.raises(IntegrityError) as excinfo:
        await db_session.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name) "
                "VALUES ('blank@example.com', 'x', '   ')"
            )
        )

    assert "users_full_name_ck" in str(excinfo.value)


async def test_a_website_without_a_scheme_is_refused(db_session):
    with pytest.raises(IntegrityError) as excinfo:
        await db_session.execute(
            text(
                "INSERT INTO shops (name, slug, website) "
                "VALUES ('Site Shop', 'site-shop', 'example.com')"
            )
        )

    assert "shops_website_ck" in str(excinfo.value)


async def test_a_slug_outside_the_pattern_is_refused(db_session):
    with pytest.raises(IntegrityError) as excinfo:
        await db_session.execute(
            text("INSERT INTO shops (name, slug) VALUES ('Bad Slug', 'Bad--Slug!')")
        )

    assert "shops_slug_ck" in str(excinfo.value)


async def test_a_role_still_assigned_cannot_be_hard_deleted(db_session):
    """ON DELETE RESTRICT: no membership may be left without a role."""

    await db_session.execute(
        text(
            "INSERT INTO users (email, password_hash, full_name) "
            "VALUES ('member@example.com', 'x', 'Member')"
        )
    )
    await db_session.execute(
        text("INSERT INTO shops (name, slug) VALUES ('Member Shop', 'member-shop')")
    )
    await db_session.execute(
        text("INSERT INTO roles (key, name) VALUES ('temp', 'Temp')")
    )
    await db_session.execute(
        text(
            "INSERT INTO memberships (user_id, shop_id, role_id) "
            "SELECT u.id, s.id, r.id FROM users u, shops s, roles r "
            "WHERE u.email = 'member@example.com' AND s.slug = 'member-shop' "
            "AND r.key = 'temp'"
        )
    )

    with pytest.raises(IntegrityError) as excinfo:
        await db_session.execute(text("DELETE FROM roles WHERE key = 'temp'"))

    assert "memberships_role_id_fkey" in str(excinfo.value)


async def test_ids_are_generated_by_the_database_when_not_supplied(db_session):
    """The server default is what makes a psql insert or a data migration work."""

    await db_session.execute(
        text(
            "INSERT INTO users (email, password_hash, full_name) "
            "VALUES ('serverdefault@example.com', 'x', 'SD')"
        )
    )
    rows = await db_session.execute(
        text("SELECT id FROM users WHERE email = 'serverdefault@example.com'")
    )

    assert rows.scalar_one() is not None
