"""Contract: the identity tables, their columns, and their constraints.

These assertions are about the shape declared in Python. Whether Postgres *enforces*
them is a separate question and is answered by the ``db``-marked tests in
``tests/integration/test_identity_schema_db.py``, which need the real database
because SQLite has no ``citext``, no partial index semantics worth trusting, and no
``gen_random_uuid``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint, Index

from app.models import metadata

EXPECTED_TABLES = {
    "users",
    "shops",
    "roles",
    "permissions",
    "memberships",
    "role_permissions",
    "refresh_tokens",
}

MIXIN_COLUMNS = {"id", "created_at", "updated_at", "deleted_at"}


def _check_names(table_name: str) -> set[str]:
    table = metadata.tables[table_name]
    return {
        str(constraint.name)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name is not None
    }


def _index_named(table_name: str, name: str) -> Index:
    table = metadata.tables[table_name]
    matches = [index for index in table.indexes if index.name == name]
    assert len(matches) == 1, f"{table_name}.{name} is declared {len(matches)} times"
    return matches[0]


def _where_clause(index: Index) -> str:
    where = index.dialect_options["postgresql"].get("where")
    assert where is not None, f"{index.name} is not partial"
    return str(where)


def test_every_identity_table_is_registered_on_the_shared_metadata():
    assert set(metadata.tables) >= EXPECTED_TABLES


class TestUsers:
    def test_carries_the_mixins(self):
        columns = set(metadata.tables["users"].c.keys())

        assert columns >= MIXIN_COLUMNS

    def test_has_the_profile_columns(self):
        columns = set(metadata.tables["users"].c.keys())

        assert {
            "email",
            "password_hash",
            "full_name",
            "bio",
            "phone",
            "job_title",
            "avatar_key",
            "avatar_updated_at",
            "last_login_at",
            "deactivated_at",
        } <= columns

    def test_has_no_is_active_flag(self):
        """One fact, one representation: liveness is the two timestamps."""

        assert "is_active" not in metadata.tables["users"].c

    def test_email_is_citext(self):
        assert metadata.tables["users"].c.email.type.__class__.__name__ == "CITEXT"

    def test_email_uniqueness_is_partial_on_deleted_at(self):
        index = _index_named("users", "users_email_live")

        assert index.unique is True
        assert "deleted_at IS NULL" in _where_clause(index)

    @pytest.mark.parametrize(
        "name",
        [
            "users_email_len",
            "users_email_lower",
            "users_full_name_ck",
            "users_bio_ck",
            "users_phone_ck",
            "users_job_title_ck",
            "users_avatar_key_ck",
        ],
    )
    def test_declares_its_check_constraints(self, name: str):
        assert name in _check_names("users")


class TestShops:
    def test_carries_the_mixins(self):
        assert set(metadata.tables["shops"].c.keys()) >= MIXIN_COLUMNS

    def test_has_the_profile_columns(self):
        columns = set(metadata.tables["shops"].c.keys())

        assert {
            "name",
            "slug",
            "description",
            "contact_email",
            "contact_phone",
            "website",
            "background_key",
            "background_updated_at",
            "is_active",
        } <= columns

    def test_keeps_is_active_alongside_the_soft_delete(self):
        """Different authors: the seller deletes, an operator suspends."""

        assert "is_active" in metadata.tables["shops"].c
        assert "deleted_at" in metadata.tables["shops"].c

    def test_slug_uniqueness_is_partial_on_deleted_at(self):
        index = _index_named("shops", "shops_slug_live")

        assert index.unique is True
        assert "deleted_at IS NULL" in _where_clause(index)

    def test_declares_its_check_constraints(self):
        assert {
            "shops_name_ck",
            "shops_slug_ck",
            "shops_description_ck",
            "shops_website_ck",
            "shops_background_key_ck",
        } <= _check_names("shops")


class TestRoles:
    def test_system_role_keys_are_uniquely_indexed_where_shop_id_is_null(self):
        index = _index_named("roles", "roles_system_key_uniq")

        assert index.unique is True
        assert "shop_id IS NULL" in _where_clause(index)

    def test_shop_role_keys_are_uniquely_indexed_per_shop(self):
        index = _index_named("roles", "roles_shop_key_uniq")

        assert index.unique is True
        assert "shop_id IS NOT NULL" in _where_clause(index)
        assert {column.name for column in index.columns} == {"shop_id", "key"}

    def test_a_system_role_cannot_be_soft_deleted(self):
        """Without this check the role could never be recreated after a soft delete."""

        assert "roles_system_role_not_deleted" in _check_names("roles")


class TestMemberships:
    def test_one_live_role_per_user_per_shop(self):
        index = _index_named("memberships", "memberships_user_shop_live")

        assert index.unique is True
        assert "deleted_at IS NULL" in _where_clause(index)
        assert {column.name for column in index.columns} == {"user_id", "shop_id"}

    def test_the_role_foreign_key_restricts_deletion(self):
        """A role that is still assigned must not vanish from under a membership."""

        foreign_key = next(iter(metadata.tables["memberships"].c.role_id.foreign_keys))

        assert foreign_key.target_fullname == "roles.id"
        assert foreign_key.ondelete == "RESTRICT"


class TestRolePermissions:
    def test_has_a_composite_primary_key(self):
        table = metadata.tables["role_permissions"]

        assert {column.name for column in table.primary_key.columns} == {
            "role_id",
            "permission_id",
        }

    def test_declares_no_lifecycle_columns(self):
        columns = set(metadata.tables["role_permissions"].c.keys())

        assert columns == {"role_id", "permission_id"}


class TestPermissions:
    def test_is_a_code_driven_vocabulary_without_a_lifecycle(self):
        columns = set(metadata.tables["permissions"].c.keys())

        assert columns == {"id", "key", "description"}


class TestRefreshTokens:
    def test_stores_only_a_digest(self):
        from sqlalchemy import String

        table = metadata.tables["refresh_tokens"]
        column_type = table.c.token_hash.type

        assert "token_hash" in table.c
        assert "token" not in table.c
        assert isinstance(column_type, String)
        assert column_type.length == 64, "the column holds a hex sha-256, not the token"

    def test_the_hash_is_unique(self):
        from sqlalchemy import UniqueConstraint

        table = metadata.tables["refresh_tokens"]
        unique_sets = {
            tuple(sorted(column.name for column in constraint.columns))
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }

        assert ("token_hash",) in unique_sets

    def test_tracks_the_session_family_and_its_replacement(self):
        columns = set(metadata.tables["refresh_tokens"].c.keys())

        assert {"family_id", "revoked_at", "replaced_by_id", "expires_at"} <= columns

    def test_replacement_is_a_self_reference(self):
        foreign_key = next(
            iter(metadata.tables["refresh_tokens"].c.replaced_by_id.foreign_keys)
        )

        assert foreign_key.target_fullname == "refresh_tokens.id"

    def test_has_no_updated_at_because_only_revocation_writes(self):
        columns = set(metadata.tables["refresh_tokens"].c.keys())

        assert "created_at" in columns
        assert "updated_at" not in columns
        assert "deleted_at" not in columns
