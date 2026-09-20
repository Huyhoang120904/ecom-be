"""Contract: identity use cases against real PostgreSQL.

These are the tests that matter most in this module, because the behaviours they pin
cannot be faked: atomic registration, refresh rotation with reuse detection, and
sessions whose shop binding is enforced server-side.
"""

from __future__ import annotations

import pytest

from app.errors.identity import (
    AccountDeactivated,
    AccountInactive,
    ConfirmationMismatch,
    EmailTaken,
    InvalidCredentials,
    InvalidToken,
    NotAMember,
    ShopNotAccessible,
)
from app.repositories import (
    membership_repository,
    refresh_token_repository,
    role_repository,
    shop_repository,
    user_repository,
)
from app.services.identity_service import IdentityService

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

        memberships = await membership_repository.list_memberships(
            db_session, session.user.id
        )
        assert [role.key for _shop, role in memberships] == ["owner"]

    async def test_stores_a_hash_of_the_supplied_password_not_the_password(
        self, db_session
    ):
        await _register(db_session)

        stored = await user_repository.find_user_by_email(
            db_session, "owner@example.com"
        )

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

        slugs = await shop_repository.list_all_shop_slugs(db_session)
        assert "second-shop" not in slugs

    async def test_the_access_token_identifies_the_new_shop(self, db_session):
        from app.config.settings import get_settings
        from app.utils.identity import decode_access_token

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

        from app.utils.identity import hash_refresh_token

        _service, first = await _register(db_session)
        service = IdentityService(db_session)
        await service.refresh(first.refresh_token)

        original = await refresh_token_repository.find_refresh_token(
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
        from app.utils.identity import hash_refresh_token

        _service, first = await _register(db_session)
        service = IdentityService(db_session)
        await service.refresh(first.refresh_token)

        with pytest.raises(InvalidToken):
            await service.refresh(first.refresh_token)

        stored = await refresh_token_repository.find_refresh_token(
            db_session, hash_refresh_token(first.refresh_token)
        )
        assert stored is not None
        assert (
            await refresh_token_repository.list_unrevoked_family(
                db_session, stored.family_id
            )
            == []
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

        from app.utils.identity import hash_refresh_token, new_refresh_token

        _service, first = await _register(db_session)
        raw, digest = new_refresh_token()
        await refresh_token_repository.create_refresh_token(
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
            await refresh_token_repository.find_refresh_token(
                db_session, hash_refresh_token(raw)
            )
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
        other = await shop_repository.create_shop(db_session, name="Someone Else")
        service = IdentityService(db_session)

        with pytest.raises(NotAMember):
            await service.switch_shop(
                user_id=session.user.id,
                shop_id=other.id,
                refresh_token=session.refresh_token,
            )

    async def test_a_suspended_shop_is_not_accessible(self, db_session):
        _service, session = await _register(db_session)
        await shop_repository.set_shop_active(db_session, session.active_shop.id, False)
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
        from app.config.settings import get_settings
        from app.utils.identity import decode_access_token

        _service, session = await _register(db_session)
        second_shop = await shop_repository.create_shop(db_session, name="Second Shop")
        owner = await role_repository.get_owner_role(db_session)
        await membership_repository.create_membership(
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
        other = await shop_repository.create_shop(db_session, name="Not Mine")
        service = IdentityService(db_session)

        with pytest.raises(ShopNotAccessible):
            await service.me(user_id=session.user.id, shop_id=other.id)

    async def test_a_deactivated_account_reports_itself_inactive(self, db_session):
        _service, session = await _register(db_session)
        await user_repository.deactivate_user(db_session, session.user)
        service = IdentityService(db_session)

        from app.errors.identity import AccountInactive

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

        unchanged = await user_repository.find_user_by_email(
            db_session, "owner@example.com"
        )
        assert unchanged is not None
        assert unchanged.deactivated_at is None

    async def test_deactivation_ends_every_session_and_blocks_sign_in(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)
        # A second session, to prove every family dies rather than just this one.
        second = await service.login(email="owner@example.com", password=PASSWORD)

        await service.deactivate(user_id=session.user.id, password=PASSWORD)

        # Both sessions report the accurate reason: the account is inactive, not that
        # the token was reused. The distinction matters to a client deciding whether
        # to prompt for credentials or to stop entirely.
        with pytest.raises(AccountInactive):
            await service.refresh(session.refresh_token)
        with pytest.raises(AccountInactive):
            await service.refresh(second.refresh_token)
        with pytest.raises(AccountDeactivated):
            await service.login(email="owner@example.com", password=PASSWORD)

    async def test_deactivation_keeps_the_email_reserved(self, db_session):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)
        await service.deactivate(user_id=session.user.id, password=PASSWORD)

        stored = await user_repository.find_user_by_email(
            db_session, "owner@example.com"
        )
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

        assert (
            await shop_repository.get_shop(db_session, session.active_shop.id)
            is not None
        )

    async def test_deleting_a_shop_soft_deletes_it_and_revokes_its_sessions(
        self, db_session
    ):
        _service, session = await _register(db_session)
        service = IdentityService(db_session)

        await service.delete_active_shop(
            shop_id=session.active_shop.id,
            confirm_shop_name=session.active_shop.name,
        )

        assert (
            await shop_repository.get_shop(db_session, session.active_shop.id) is None
        )
        assert (
            await membership_repository.list_memberships(db_session, session.user.id)
            == []
        )
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


class TestBuyerAndAdminServices:
    async def test_buyer_registration_and_login(self, db_session):
        service = IdentityService(db_session)
        session = await service.register(
            email="purebuyer@example.com",
            password=PASSWORD,
            full_name="Pure Buyer",
            shop_name=None,
        )
        assert session.user.email == "purebuyer@example.com"
        assert session.active_shop is None
        assert session.memberships == []
        assert session.audience == "storefront"

        # Login as buyer
        login_session = await service.login(
            email="purebuyer@example.com",
            password=PASSWORD,
            audience="storefront",
        )
        assert login_session.active_shop is None
        assert login_session.audience == "storefront"

        # Refresh buyer session
        refreshed = await service.refresh(login_session.refresh_token)
        assert refreshed.active_shop is None
        assert refreshed.audience == "storefront"

        # Calling me as buyer
        user, shop, memberships, _permissions = await service.me(
            user_id=session.user.id, shop_id=None
        )
        assert user.email == "purebuyer@example.com"
        assert shop is None
        assert memberships == []

    async def test_admin_login_requires_platform_membership(self, db_session):
        from app.errors.identity import Forbidden

        service = IdentityService(db_session)
        # Register regular user without platform membership
        await service.register(
            email="regular_buyer@example.com",
            password=PASSWORD,
            full_name="Regular Buyer",
            shop_name=None,
        )
        with pytest.raises(Forbidden):
            await service.login(
                email="regular_buyer@example.com",
                password=PASSWORD,
                audience="admin",
            )

    async def test_admin_login_and_refresh_with_platform_membership(self, db_session):
        from app.cli import create_admin_account

        admin_user = await create_admin_account(
            db_session,
            email="sysadmin_serv@example.com",
            password=PASSWORD,
            full_name="Sys Admin Service",
        )
        service = IdentityService(db_session)
        session = await service.login(
            email=admin_user.email,
            password=PASSWORD,
            audience="admin",
        )
        assert session.active_shop is None
        assert session.audience == "admin"
        assert "platform:metrics:read" in session.permissions

        # Refresh admin session
        refreshed = await service.refresh(session.refresh_token)
        assert refreshed.audience == "admin"
        assert refreshed.active_shop is None
        assert "platform:metrics:read" in refreshed.permissions

        # Calling me as admin
        user, shop, _memberships, permissions = await service.me(
            user_id=admin_user.id, shop_id=None
        )
        assert user.email == admin_user.email
        assert shop is None
        assert "platform:metrics:read" in permissions

    async def test_cms_login_skips_a_suspended_shop(self, db_session):
        """The oldest membership is only preferred while its shop is usable."""

        service = IdentityService(db_session)
        first = await service.register(
            email="two_shops@example.com",
            password=PASSWORD,
            full_name="Two Shops",
            shop_name="First Shop",
        )
        second = await shop_repository.create_shop(db_session, name="Second Shop")
        owner_role = await role_repository.get_owner_role(db_session)
        await membership_repository.create_membership(
            db_session,
            user_id=first.user.id,
            shop_id=second.id,
            role_id=owner_role.id,
        )
        assert first.active_shop is not None
        await shop_repository.set_shop_active(db_session, first.active_shop.id, False)

        session = await service.login(
            email="two_shops@example.com", password=PASSWORD, audience="cms"
        )

        assert session.active_shop is not None
        assert session.active_shop.id == second.id

    async def test_cms_login_is_refused_when_every_shop_is_suspended(self, db_session):
        service = IdentityService(db_session)
        registered = await service.register(
            email="suspended_only@example.com",
            password=PASSWORD,
            full_name="Suspended Only",
            shop_name="Suspended Shop",
        )
        assert registered.active_shop is not None
        await shop_repository.set_shop_active(
            db_session, registered.active_shop.id, False
        )

        with pytest.raises(AccountInactive):
            await service.login(
                email="suspended_only@example.com",
                password=PASSWORD,
                audience="cms",
            )

    async def test_refresh_refuses_when_the_bound_shop_was_suspended(self, db_session):
        """The refusal kills the whole family, not only the token that was presented."""

        from app.utils.identity import hash_refresh_token

        service = IdentityService(db_session)
        session = await service.register(
            email="refresh_shop@example.com",
            password=PASSWORD,
            full_name="Refresh Shop",
            shop_name="Refresh Shop",
        )
        # Rotate once, so the family holds a live row *and* a replaced one: a refusal
        # that only revoked the presented row would leave the live sibling usable.
        rotated = await service.refresh(session.refresh_token)
        assert rotated.active_shop is not None
        live = await refresh_token_repository.find_refresh_token(
            db_session, hash_refresh_token(rotated.refresh_token)
        )
        assert live is not None
        # A *second* live row in the same family, so a refusal that revoked only the
        # token it was handed would leave something usable behind and fail here.
        await refresh_token_repository.create_refresh_token(
            db_session,
            user_id=live.user_id,
            active_shop_id=live.active_shop_id,
            audience=live.audience,
            token_hash=hash_refresh_token("sibling-token"),
            expires_at=live.expires_at,
            family_id=live.family_id,
        )
        await shop_repository.set_shop_active(db_session, rotated.active_shop.id, False)

        with pytest.raises(ShopNotAccessible):
            await service.refresh(rotated.refresh_token)

        presented = await refresh_token_repository.find_refresh_token(
            db_session, hash_refresh_token(rotated.refresh_token)
        )
        assert presented is not None and presented.revoked_at is not None
        sibling = await refresh_token_repository.find_refresh_token(
            db_session, hash_refresh_token("sibling-token")
        )
        assert sibling is not None and sibling.revoked_at is not None
        assert (
            await refresh_token_repository.list_unrevoked_family(
                db_session, presented.family_id
            )
            == []
        )

        with pytest.raises(InvalidToken):
            await service.refresh(rotated.refresh_token)

    async def test_refresh_refuses_when_the_platform_role_was_revoked(self, db_session):
        from app.cli import create_admin_account
        from app.errors.identity import Forbidden
        from app.utils.identity import hash_refresh_token

        admin_user = await create_admin_account(
            db_session,
            email="demoted_admin@example.com",
            password=PASSWORD,
            full_name="Demoted Admin",
        )
        service = IdentityService(db_session)
        session = await service.login(
            email=admin_user.email, password=PASSWORD, audience="admin"
        )
        rotated = await service.refresh(session.refresh_token)
        live = await refresh_token_repository.find_refresh_token(
            db_session, hash_refresh_token(rotated.refresh_token)
        )
        assert live is not None
        await refresh_token_repository.create_refresh_token(
            db_session,
            user_id=live.user_id,
            active_shop_id=live.active_shop_id,
            audience=live.audience,
            token_hash=hash_refresh_token("admin-sibling-token"),
            expires_at=live.expires_at,
            family_id=live.family_id,
        )

        await membership_repository.soft_delete_platform_membership(
            db_session, admin_user.id
        )

        with pytest.raises(Forbidden):
            await service.refresh(rotated.refresh_token)

        presented = await refresh_token_repository.find_refresh_token(
            db_session, hash_refresh_token(rotated.refresh_token)
        )
        assert presented is not None and presented.revoked_at is not None
        sibling = await refresh_token_repository.find_refresh_token(
            db_session, hash_refresh_token("admin-sibling-token")
        )
        assert sibling is not None and sibling.revoked_at is not None
        assert (
            await refresh_token_repository.list_unrevoked_family(
                db_session, presented.family_id
            )
            == []
        )

        with pytest.raises(InvalidToken):
            await service.refresh(rotated.refresh_token)

    @pytest.mark.parametrize("bad_audience", ["legacy", ""])
    async def test_refresh_refuses_an_audience_the_software_does_not_recognise(
        self, db_session, bad_audience
    ):
        """A corrupt stored value must not be replayed as a wider perimeter.

        The session is shop-bound and one of the stored values is falsy, because the
        fallback this guards against (``stored.audience or "cms"``) would turn ``""``
        into a CMS session for that shop — the widening, not just the wrong label.
        """

        import uuid
        from datetime import UTC, datetime, timedelta

        from app.utils.identity import hash_refresh_token

        service = IdentityService(db_session)
        registered = await service.register(
            email=f"corrupt_audience_{bad_audience or 'empty'}@example.com",
            password=PASSWORD,
            full_name="Corrupt Audience",
            shop_name="Corrupt Shop",
        )
        assert registered.active_shop is not None
        await refresh_token_repository.create_refresh_token(
            db_session,
            user_id=registered.user.id,
            active_shop_id=registered.active_shop.id,
            audience=bad_audience,
            token_hash=hash_refresh_token("corrupt-audience-token"),
            expires_at=datetime.now(UTC) + timedelta(days=30),
            family_id=uuid.uuid4(),
        )

        with pytest.raises(InvalidToken):
            await service.refresh("corrupt-audience-token")
