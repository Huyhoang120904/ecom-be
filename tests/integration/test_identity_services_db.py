"""Contract: identity use cases against real PostgreSQL.

These are the tests that matter most in this module, because the behaviours they pin
cannot be faked: atomic registration, refresh rotation with reuse detection, and
sessions whose shop binding is enforced server-side.
"""

from __future__ import annotations

import pytest

from ecom_be.modules.identity import repository
from ecom_be.modules.identity.errors import (
    AccountDeactivated,
    ConfirmationMismatch,
    EmailTaken,
    InvalidCredentials,
    InvalidToken,
    NotAMember,
    ShopNotAccessible,
)
from ecom_be.modules.identity.services import IdentityService

pytestmark = [pytest.mark.anyio, pytest.mark.db]

PASSWORD = "a-perfectly-fine-password"


async def _register(
    db_session,
    *,
    email: str = "owner@example.com",
    shop_name: str = "Owner Shop",
):
    service = IdentityService(db_session)
    session = await service.register(
        email=email, password=PASSWORD, full_name="Owner Person", shop_name=shop_name
    )
    return service, session


class TestRegister:
    async def test_creates_user_shop_and_owner_membership_in_one_commit(
        self, db_session
    ):
        _service, session = await _register(db_session)

        assert session.user.email == "owner@example.com"
        assert session.active_shop.slug == "owner-shop"
        assert "shop:update" in session.permissions
        assert len(session.permissions) == 9
        assert session.refresh_token

        memberships = await repository.list_memberships(db_session, session.user.id)
        assert [role.key for _shop, role in memberships] == ["owner"]

    async def test_stores_a_hash_of_the_supplied_password_not_the_password(
        self, db_session
    ):
        await _register(db_session)

        stored = await repository.find_user_by_email(db_session, "owner@example.com")

        assert stored is not None
        assert stored.password_hash.startswith("$argon2id$")
        assert PASSWORD not in stored.password_hash

    async def test_a_taken_email_is_refused_and_creates_no_second_shop(
        self, db_session
    ):
        await _register(db_session, email="dup@example.com", shop_name="First Shop")

        with pytest.raises(EmailTaken):
            await _register(
                db_session, email="dup@example.com", shop_name="Second Shop"
            )

        slugs = await repository.list_all_shop_slugs(db_session)
        assert "second-shop" not in slugs

    async def test_the_access_token_identifies_the_new_shop(self, db_session):
        from ecom_be.core.config import get_settings
        from ecom_be.modules.identity.utils import decode_access_token

        _service, session = await _register(db_session)
        claims = decode_access_token(get_settings(), session.access_token)

        assert claims["sub"] == str(session.user.id)
        assert claims["sid"] == str(session.active_shop.id)

    async def test_registration_produces_exactly_one_refresh_row(self, db_session):
        from sqlalchemy import text

        _service, session = await _register(db_session)
        rows = await db_session.execute(
            text("SELECT count(*) FROM refresh_tokens WHERE user_id = :uid"),
            {"uid": session.user.id},
        )

        assert rows.scalar_one() == 1


class TestLogin:
    async def test_a_correct_password_starts_a_session(self, db_session):
        await _register(db_session)
        service = IdentityService(db_session)

        session = await service.login(email="owner@example.com", password=PASSWORD)

        assert session.user.email == "owner@example.com"
        assert session.access_token

    async def test_a_wrong_password_and_an_unknown_email_are_indistinguishable(
        self, db_session
    ):
        await _register(db_session)
        service = IdentityService(db_session)

        with pytest.raises(InvalidCredentials):
            await service.login(
                email="owner@example.com", password="wrong-password-entirely"
            )
        with pytest.raises(InvalidCredentials):
            await service.login(
                email="nobody@example.com", password="wrong-password-entirely"
            )

    async def test_login_is_case_insensitive_on_the_email(self, db_session):
        await _register(db_session)
        service = IdentityService(db_session)

        session = await service.login(email="OWNER@EXAMPLE.COM", password=PASSWORD)

        assert session.user.email == "owner@example.com"

    async def test_login_records_last_login(self, db_session):
        await _register(db_session)
        service = IdentityService(db_session)

        session = await service.login(email="owner@example.com", password=PASSWORD)

        assert session.user.last_login_at is not None


class TestRefreshRotation:
    async def test_a_refresh_rotates_the_access_token(self, db_session):
        _service, first = await _register(db_session)
        service = IdentityService(db_session)

        rotated = await service.refresh(first.refresh_token)

        assert rotated.access_token != first.access_token
        assert rotated.refresh_token != first.refresh_token

    async def test_the_old_token_still_resolves_its_family(self, db_session):
        """Rotation adds a row; it does not orphan the original."""

        from ecom_be.modules.identity.utils import hash_refresh_token

        _service, first = await _register(db_session)
        service = IdentityService(db_session)
        await service.refresh(first.refresh_token)

        original = await repository.find_refresh_token(
            db_session, hash_refresh_token(first.refresh_token)
        )

        assert original is not None
        assert original.revoked_at is not None
        assert original.replaced_by_id is not None

    async def test_reuse_revokes_the_entire_family(self, db_session):
        _service, first = await _register(db_session)
        service = IdentityService(db_session)
        rotated = await service.refresh(first.refresh_token)

        # Replaying the already-rotated value is the reuse signal.
        with pytest.raises(InvalidToken):
            await service.refresh(first.refresh_token)

        # The legitimate token dies with the family.
        with pytest.raises(InvalidToken):
            await service.refresh(rotated.refresh_token)

    async def test_reuse_leaves_no_unrevoked_row_in_the_family(self, db_session):
        from ecom_be.modules.identity.utils import hash_refresh_token

        _service, first = await _register(db_session)
        service = IdentityService(db_session)
        await service.refresh(first.refresh_token)

        with pytest.raises(InvalidToken):
            await service.refresh(first.refresh_token)

        stored = await repository.find_refresh_token(
            db_session, hash_refresh_token(first.refresh_token)
        )
        assert stored is not None
        assert (
            await repository.list_unrevoked_family(db_session, stored.family_id) == []
        )

    async def test_an_unknown_token_is_refused(self, db_session):
        service = IdentityService(db_session)

        with pytest.raises(InvalidToken):
            await service.refresh("no-such-token")

    async def test_a_missing_token_is_refused(self, db_session):
        service = IdentityService(db_session)

        with pytest.raises(InvalidToken):
            await service.refresh(None)

    async def test_an_expired_token_is_refused(self, db_session):
        from datetime import UTC, datetime, timedelta

        from ecom_be.modules.identity.utils import hash_refresh_token, new_refresh_token

        _service, first = await _register(db_session)
        raw, digest = new_refresh_token()
        await repository.create_refresh_token(
            db_session,
            user_id=first.user.id,
            active_shop_id=first.active_shop.id,
            token_hash=digest,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        service = IdentityService(db_session)

        with pytest.raises(InvalidToken):
            await service.refresh(raw)

        assert (
            await repository.find_refresh_token(db_session, hash_refresh_token(raw))
            is not None
        )


class TestLogout:
    async def test_logout_revokes_the_family(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        await service.logout(session.refresh_token)

        with pytest.raises(InvalidToken):
            await service.refresh(session.refresh_token)

    async def test_logout_without_a_token_is_silent(self, db_session):
        service = IdentityService(db_session)

        await service.logout(None)
        await service.logout("unrecognized-token")


class TestSwitchShop:
    async def test_a_non_member_shop_is_refused(self, db_session):
        _service, session = await _register(db_session)
        other = await repository.create_shop(db_session, name="Someone Else")
        service = IdentityService(db_session)

        with pytest.raises(NotAMember):
            await service.switch_shop(
                user_id=session.user.id,
                shop_id=other.id,
                refresh_token=session.refresh_token,
            )

    async def test_a_suspended_shop_is_not_accessible(self, db_session):
        _service, session = await _register(db_session)
        await repository.set_shop_active(db_session, session.active_shop.id, False)
        service = IdentityService(db_session)

        with pytest.raises(ShopNotAccessible):
            await service.switch_shop(
                user_id=session.user.id,
                shop_id=session.active_shop.id,
                refresh_token=session.refresh_token,
            )

    async def test_switching_rebinds_the_token_and_rotates_the_refresh(
        self, db_session
    ):
        from ecom_be.core.config import get_settings
        from ecom_be.modules.identity.utils import decode_access_token

        _service, session = await _register(db_session)
        second_shop = await repository.create_shop(db_session, name="Second Shop")
        owner = await repository.get_owner_role(db_session)
        await repository.create_membership(
            db_session,
            user_id=session.user.id,
            shop_id=second_shop.id,
            role_id=owner.id,
        )
        service = IdentityService(db_session)

        switched = await service.switch_shop(
            user_id=session.user.id,
            shop_id=second_shop.id,
            refresh_token=session.refresh_token,
        )

        claims = decode_access_token(get_settings(), switched.access_token)
        assert claims["sid"] == str(second_shop.id)
        assert switched.refresh_token != session.refresh_token
        # The previous refresh value is now rotated out.
        with pytest.raises(InvalidToken):
            await service.refresh(session.refresh_token)


class TestMe:
    async def test_returns_memberships_and_effective_permissions(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        user, shop, memberships, permissions = await service.me(
            user_id=session.user.id, shop_id=session.active_shop.id
        )

        assert user.email == "owner@example.com"
        assert shop.id == session.active_shop.id
        assert len(memberships) == 1
        assert "membership:manage" in permissions

    async def test_a_shop_the_caller_does_not_belong_to_is_not_accessible(
        self, db_session
    ):
        _service, session = await _register(db_session)
        other = await repository.create_shop(db_session, name="Not Mine")
        service = IdentityService(db_session)

        with pytest.raises(ShopNotAccessible):
            await service.me(user_id=session.user.id, shop_id=other.id)

    async def test_a_deactivated_account_reports_itself_inactive(self, db_session):
        _service, session = await _register(db_session)
        await repository.deactivate_user(db_session, session.user)
        service = IdentityService(db_session)

        from ecom_be.modules.identity.errors import AccountInactive

        with pytest.raises(AccountInactive):
            await service.me(user_id=session.user.id, shop_id=session.active_shop.id)


class TestProfileUpdate:
    async def test_only_the_supplied_keys_change(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        user = await service.update_profile(
            user_id=session.user.id, changes={"bio": "I sell lamps."}
        )

        assert user.bio == "I sell lamps."
        assert user.full_name == "Owner Person"
        assert user.job_title is None

    async def test_an_explicit_none_clears_a_nullable_field(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        await service.update_profile(
            user_id=session.user.id, changes={"bio": "Lamps.", "phone": "+13128471928"}
        )
        user = await service.update_profile(
            user_id=session.user.id, changes={"bio": None}
        )

        assert user.bio is None
        assert user.phone == "+13128471928", "an omitted key is untouched"


class TestDeactivation:
    async def test_a_wrong_password_changes_nothing(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        with pytest.raises(InvalidCredentials):
            await service.deactivate(
                user_id=session.user.id, password="not-the-password"
            )

        unchanged = await repository.find_user_by_email(db_session, "owner@example.com")
        assert unchanged is not None
        assert unchanged.deactivated_at is None

    async def test_deactivation_ends_every_session_and_blocks_sign_in(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)
        # A second session, to prove every family dies rather than just this one.
        second = await service.login(email="owner@example.com", password=PASSWORD)

        await service.deactivate(user_id=session.user.id, password=PASSWORD)

        with pytest.raises(InvalidToken):
            await service.refresh(session.refresh_token)
        with pytest.raises(InvalidToken):
            await service.refresh(second.refresh_token)
        with pytest.raises(AccountDeactivated):
            await service.login(email="owner@example.com", password=PASSWORD)

    async def test_deactivation_keeps_the_email_reserved(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)
        await service.deactivate(user_id=session.user.id, password=PASSWORD)

        stored = await repository.find_user_by_email(db_session, "owner@example.com")
        assert stored is not None, "deactivation is not deletion"
        assert stored.deleted_at is None

        with pytest.raises(EmailTaken):
            await _register(db_session, email="owner@example.com", shop_name="New Shop")


class TestShops:
    async def test_renaming_a_shop_leaves_the_slug_alone(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        shop = await service.update_active_shop(
            shop_id=session.active_shop.id, changes={"name": "A Different Name"}
        )

        assert shop.name == "A Different Name"
        assert shop.slug == "owner-shop"

    async def test_a_background_key_is_set_and_cleared(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        with_key = await service.set_shop_background(
            shop_id=session.active_shop.id, key="shops/x/bg.webp"
        )
        assert with_key.background_key == "shops/x/bg.webp"
        assert with_key.background_updated_at is not None

        cleared = await service.set_shop_background(
            shop_id=session.active_shop.id, key=None
        )
        assert cleared.background_key is None

    async def test_deleting_a_shop_requires_the_exact_name(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        with pytest.raises(ConfirmationMismatch):
            await service.delete_active_shop(
                shop_id=session.active_shop.id, confirm_shop_name="Not The Name"
            )

        assert await repository.get_shop(db_session, session.active_shop.id) is not None

    async def test_deleting_a_shop_soft_deletes_it_and_revokes_its_sessions(
        self, db_session
    ):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        await service.delete_active_shop(
            shop_id=session.active_shop.id,
            confirm_shop_name=session.active_shop.name,
        )

        assert await repository.get_shop(db_session, session.active_shop.id) is None
        assert await repository.list_memberships(db_session, session.user.id) == []
        with pytest.raises(InvalidToken):
            await service.refresh(session.refresh_token)

    async def test_the_shop_row_survives_deletion(self, db_session):
        from sqlalchemy import text

        _service, session = await _register(db_session)
        service = IdentityService(db_session)
        await service.delete_active_shop(
            shop_id=session.active_shop.id,
            confirm_shop_name=session.active_shop.name,
        )

        rows = await db_session.execute(
            text("SELECT deleted_at FROM shops WHERE id = :sid"),
            {"sid": session.active_shop.id},
        )

        assert rows.scalar_one() is not None, "retired, not purged"
