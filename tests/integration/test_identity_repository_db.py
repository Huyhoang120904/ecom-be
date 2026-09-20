"""Contract: repository behaviour against real PostgreSQL.

The interesting cases are the ones a unit test cannot reach: the case-insensitive
email lookup, the partial unique indexes behind soft delete, and the
effective-permission projection with every soft-delete predicate in place.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.repositories import (
    membership_repository,
    refresh_token_repository,
    role_repository,
    shop_repository,
    user_repository,
)
from app.utils.identity import hash_refresh_token

pytestmark = [pytest.mark.anyio, pytest.mark.db]


async def _make_user(db_session, email: str = "a@example.com"):
    return await user_repository.create_user(
        db_session, email=email, password_hash="x", full_name="A Person"
    )


class TestUsers:
    async def test_finds_a_user_regardless_of_email_case(self, db_session):
        """``citext`` does the folding, so a caller may pass any casing."""

        user = await _make_user(db_session, "a@example.com")

        found = await user_repository.find_user_by_email(db_session, "A@EXAMPLE.COM")

        assert found is not None and found.id == user.id

    async def test_a_soft_deleted_user_is_invisible_to_the_lookup(self, db_session):
        user = await _make_user(db_session)

        await user_repository.soft_delete_user(db_session, user)

        assert (
            await user_repository.find_user_by_email(db_session, "a@example.com")
            is None
        )

    async def test_soft_deleting_releases_the_email_for_reuse(self, db_session):
        first = await _make_user(db_session, "reuse@example.com")

        await user_repository.soft_delete_user(db_session, first)
        second = await _make_user(db_session, "reuse@example.com")

        assert second.id != first.id

    async def test_a_profile_update_writes_only_the_given_keys(self, db_session):
        user = await _make_user(db_session)

        await user_repository.update_user_profile(
            db_session, user, {"bio": "Lamps.", "job_title": "Owner"}
        )

        assert user.bio == "Lamps."
        assert user.job_title == "Owner"
        assert user.full_name == "A Person"

    async def test_clearing_a_nullable_field_is_distinct_from_leaving_it(
        self, db_session
    ):
        user = await _make_user(db_session)
        await user_repository.update_user_profile(db_session, user, {"bio": "Lamps."})

        await user_repository.update_user_profile(db_session, user, {"bio": None})

        assert user.bio is None
        assert user.full_name == "A Person"

    async def test_deactivation_does_not_release_the_email(self, db_session):
        user = await _make_user(db_session, "keep@example.com")

        await user_repository.deactivate_user(db_session, user)

        assert user.deactivated_at is not None
        assert user.deleted_at is None
        assert (
            await user_repository.find_user_by_email(db_session, "keep@example.com")
        ) is not None


class TestShops:
    async def test_suffixes_a_colliding_slug(self, db_session):
        first = await shop_repository.create_shop(db_session, name="Hoang Goods")
        second = await shop_repository.create_shop(db_session, name="Hoang Goods")

        assert first.slug == "hoang-goods"
        assert second.slug == "hoang-goods-2"

    async def test_a_soft_deleted_slug_does_not_force_a_suffix(self, db_session):
        """The partial index releases the slug, so the suffix counter restarts."""

        first = await shop_repository.create_shop(db_session, name="Reused Name")
        await shop_repository.soft_delete_shop(db_session, first)

        second = await shop_repository.create_shop(db_session, name="Reused Name")

        assert second.slug == "reused-name"

    async def test_slugifies_a_non_ascii_name(self, db_session):
        shop = await shop_repository.create_shop(db_session, name="Cửa hàng Hoàng")

        assert shop.slug == "cua-hang-hoang"

    async def test_a_shop_update_never_touches_the_slug(self, db_session):
        shop = await shop_repository.create_shop(db_session, name="Original Name")

        await shop_repository.update_shop_profile(
            db_session, shop, {"name": "A Different Name"}
        )

        assert shop.name == "A Different Name"
        assert shop.slug == "original-name"

    async def test_an_operator_can_suspend_a_shop(self, db_session):
        shop = await shop_repository.create_shop(db_session, name="Suspendable")

        await shop_repository.set_shop_active(db_session, shop.id, False)
        await db_session.refresh(shop)

        assert shop.is_active is False


class TestMembershipsAndPermissions:
    async def test_resolves_the_role_and_its_permission_keys(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Perm Shop")
        owner = await role_repository.get_owner_role(db_session)
        await membership_repository.create_membership(
            db_session, user_id=user.id, shop_id=shop.id, role_id=owner.id
        )

        resolved = await membership_repository.effective_permissions(
            db_session, user_id=user.id, shop_id=shop.id
        )

        assert resolved is not None
        _user, role, keys = resolved
        assert role.key == "owner"
        assert "shop:update" in keys
        assert len(keys) == 9

    async def test_a_viewer_resolves_fewer_keys(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Viewer Shop")
        viewer = await role_repository.get_role_by_key(db_session, "viewer")
        assert viewer is not None
        await membership_repository.create_membership(
            db_session, user_id=user.id, shop_id=shop.id, role_id=viewer.id
        )

        resolved = await membership_repository.effective_permissions(
            db_session, user_id=user.id, shop_id=shop.id
        )

        assert resolved is not None
        keys = resolved[2]
        assert "shop:update" not in keys
        assert keys == sorted(keys)

    async def test_no_membership_resolves_to_none(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Unrelated")

        assert (
            await membership_repository.effective_permissions(
                db_session, user_id=user.id, shop_id=shop.id
            )
        ) is None

    async def test_a_revoked_membership_takes_effect_immediately(self, db_session):
        """No caching: the next resolution already sees the change."""

        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Revoked Shop")
        owner = await role_repository.get_owner_role(db_session)
        membership = await membership_repository.create_membership(
            db_session, user_id=user.id, shop_id=shop.id, role_id=owner.id
        )

        membership.deleted_at = datetime.now(UTC)
        await db_session.flush()

        assert (
            await membership_repository.effective_permissions(
                db_session, user_id=user.id, shop_id=shop.id
            )
        ) is None

    async def test_a_deactivated_user_resolves_to_none(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Deact Shop")
        owner = await role_repository.get_owner_role(db_session)
        await membership_repository.create_membership(
            db_session, user_id=user.id, shop_id=shop.id, role_id=owner.id
        )

        await user_repository.deactivate_user(db_session, user)

        assert (
            await membership_repository.effective_permissions(
                db_session, user_id=user.id, shop_id=shop.id
            )
        ) is None

    async def test_a_deleted_shop_makes_its_memberships_unresolvable(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Gone Shop")
        owner = await role_repository.get_owner_role(db_session)
        await membership_repository.create_membership(
            db_session, user_id=user.id, shop_id=shop.id, role_id=owner.id
        )

        await shop_repository.soft_delete_shop(db_session, shop)

        assert (
            await membership_repository.effective_permissions(
                db_session, user_id=user.id, shop_id=shop.id
            )
        ) is None

    async def test_memberships_are_listed_oldest_first(self, db_session):
        user = await _make_user(db_session)
        owner = await role_repository.get_owner_role(db_session)
        for name in ("First Shop", "Second Shop", "Third Shop"):
            shop = await shop_repository.create_shop(db_session, name=name)
            await membership_repository.create_membership(
                db_session, user_id=user.id, shop_id=shop.id, role_id=owner.id
            )

        memberships = await membership_repository.list_memberships(db_session, user.id)

        assert [shop.name for shop, _role in memberships] == [
            "First Shop",
            "Second Shop",
            "Third Shop",
        ]

    async def test_demoting_a_membership_changes_the_resolved_keys(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Demote Shop")
        owner = await role_repository.get_owner_role(db_session)
        await membership_repository.create_membership(
            db_session, user_id=user.id, shop_id=shop.id, role_id=owner.id
        )

        await membership_repository.set_membership_role_by_key(
            db_session,
            user_email=user.email,
            shop_id=shop.id,
            role_key="viewer",
        )
        resolved = await membership_repository.effective_permissions(
            db_session, user_id=user.id, shop_id=shop.id
        )

        assert resolved is not None
        assert resolved[1].key == "viewer"
        assert "shop:update" not in resolved[2]


class TestPlatformMemberships:
    """Platform roles hang off a membership with no shop, so the lookup differs."""

    async def _grant_sys_admin(self, db_session, user):
        admin_role = await role_repository.get_sys_admin_role(db_session)
        return await membership_repository.create_membership(
            db_session, user_id=user.id, shop_id=None, role_id=admin_role.id
        )

    async def test_resolves_the_platform_role_and_its_permission_keys(self, db_session):
        user = await _make_user(db_session, "platform_op@example.com")
        await self._grant_sys_admin(db_session, user)

        resolved = await membership_repository.find_platform_membership(
            db_session, user.id
        )

        assert resolved is not None
        role, permissions = resolved
        assert role.key == "sys_admin"
        assert role.shop_id is None
        assert "platform:metrics:read" in permissions
        assert "platform:shops:manage" in permissions

    async def test_a_shop_membership_is_not_a_platform_membership(self, db_session):
        user = await _make_user(db_session, "seller_only@example.com")
        shop = await shop_repository.create_shop(db_session, name="Seller Shop")
        owner_role = await role_repository.get_owner_role(db_session)
        await membership_repository.create_membership(
            db_session, user_id=user.id, shop_id=shop.id, role_id=owner_role.id
        )

        assert (
            await membership_repository.find_platform_membership(db_session, user.id)
            is None
        )

    async def test_a_revoked_platform_membership_resolves_to_none(self, db_session):
        user = await _make_user(db_session, "revoked_admin@example.com")
        membership = await self._grant_sys_admin(db_session, user)
        membership.deleted_at = datetime.now(UTC)
        await db_session.flush()

        assert (
            await membership_repository.find_platform_membership(db_session, user.id)
            is None
        )

    async def test_the_seeded_sys_admin_role_is_platform_owned(self, db_session):
        """Found by key, owned by no shop: what the admin login path asserts."""

        role = await role_repository.get_sys_admin_role(db_session)

        assert role.key == "sys_admin"
        assert role.shop_id is None


class TestRefreshTokens:
    async def _issue(self, db_session, user, shop, raw: str = "opaque-token"):
        return await refresh_token_repository.create_refresh_token(
            db_session,
            user_id=user.id,
            active_shop_id=shop.id,
            token_hash=hash_refresh_token(raw),
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )

    async def test_a_token_is_found_by_its_digest(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Token Shop")
        issued = await self._issue(db_session, user, shop)

        found = await refresh_token_repository.find_refresh_token(
            db_session, hash_refresh_token("opaque-token")
        )

        assert found is not None and found.id == issued.id

    async def test_an_unknown_digest_finds_nothing(self, db_session):
        assert (
            await refresh_token_repository.find_refresh_token(
                db_session, hash_refresh_token("nope")
            )
        ) is None

    async def test_a_token_records_the_audience_it_was_issued_for(self, db_session):
        """The refresh flow replays this value, so it has to survive the round trip."""

        user = await _make_user(db_session)
        issued = await refresh_token_repository.create_refresh_token(
            db_session,
            user_id=user.id,
            active_shop_id=None,
            audience="storefront",
            token_hash=hash_refresh_token("buyer-token"),
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )

        assert issued.audience == "storefront"
        assert issued.active_shop_id is None

    async def test_the_raw_token_is_never_stored(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Raw Shop")
        await self._issue(db_session, user, shop, "the-raw-value")

        from sqlalchemy import text

        rows = await db_session.execute(text("SELECT token_hash FROM refresh_tokens"))
        stored = [row[0] for row in rows]

        assert stored
        assert all("the-raw-value" not in value for value in stored)

    async def test_revoking_a_family_revokes_only_that_family(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Family Shop")
        first = await self._issue(db_session, user, shop, "one")
        other_family = await refresh_token_repository.create_refresh_token(
            db_session,
            user_id=user.id,
            active_shop_id=shop.id,
            token_hash=hash_refresh_token("other"),
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )

        revoked = await refresh_token_repository.revoke_family(
            db_session, first.family_id
        )

        assert revoked == 1
        assert (
            await refresh_token_repository.list_unrevoked_family(
                db_session, first.family_id
            )
            == []
        )
        assert (
            len(
                await refresh_token_repository.list_unrevoked_family(
                    db_session, other_family.family_id
                )
            )
            == 1
        )

    async def test_revoking_every_family_for_a_user(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="All Shop")
        await self._issue(db_session, user, shop, "a")
        await self._issue(db_session, user, shop, "b")

        revoked = await refresh_token_repository.revoke_all_families_for_user(
            db_session, user.id
        )

        assert revoked == 2

    async def test_revoking_the_families_bound_to_a_shop(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Bound Shop")
        other = await shop_repository.create_shop(db_session, name="Elsewhere Shop")
        await self._issue(db_session, user, shop, "bound")
        await refresh_token_repository.create_refresh_token(
            db_session,
            user_id=user.id,
            active_shop_id=other.id,
            token_hash=hash_refresh_token("elsewhere"),
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )

        revoked = await refresh_token_repository.revoke_families_for_shop(
            db_session, shop.id
        )

        assert revoked == 1

    async def test_expired_tokens_are_pruned_lazily(self, db_session):
        user = await _make_user(db_session)
        shop = await shop_repository.create_shop(db_session, name="Expiry Shop")
        stale = await refresh_token_repository.create_refresh_token(
            db_session,
            user_id=user.id,
            active_shop_id=shop.id,
            token_hash=hash_refresh_token("stale"),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )

        deleted = await refresh_token_repository.delete_expired_refresh_tokens(
            db_session
        )

        assert deleted >= 1
        assert (
            await refresh_token_repository.find_refresh_token(
                db_session, stale.token_hash
            )
            is None
        )
