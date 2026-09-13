"""Authentication use cases: registration, sign-in, rotation, sign-out, switching.

The service layer decides *what* happens and where a transaction ends. It never
imports FastAPI, never builds a URL, and never touches an HTTP header: cookie
handling is transport and stays in the router, which is what keeps ``SameSite``,
``Path``, and ``Secure`` in one place instead of threaded through a use case.

Two rules are load-bearing:

* Services return schema-shaped results, never raw rows. The contract is the
  boundary, and passing an ORM object out is how a lazy load ends up in a response.
* A service commits. Repositories never do, so a multi-step use case can be atomic:
  ``register`` writes a user, a shop, and a membership in one transaction and commits
  once, which is why a failure cannot leave a user with no shop.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.config.settings import Settings, get_settings
from ecom_be.errors.identity import (
    AccountDeactivated,
    AccountInactive,
    EmailTaken,
    InvalidCredentials,
    InvalidToken,
    NotAMember,
    ShopNotAccessible,
)
from ecom_be.infrastructure.security.passwords import (
    hash_password,
    verify_dummy,
    verify_password,
)
from ecom_be.repositories import (
    membership_repository,
    refresh_token_repository,
    role_repository,
    shop_repository,
    user_repository,
)
from ecom_be.services.session_service import Session, issue_session
from ecom_be.utils import identity as utils

logger = logging.getLogger(__name__)


class AuthService:
    """Credentials and sessions: registration, sign-in, rotation, switch, sign-out."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings if settings is not None else get_settings()

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        shop_name: str,
    ) -> Session:
        """Create the account, its first shop, and the owner membership, then sign in.

        One commit at the end. A failure anywhere before it leaves nothing behind,
        so a seller cannot end up with an account that has no shop.
        """

        if await user_repository.find_user_by_email(self._session, email) is not None:
            raise EmailTaken

        try:
            user = await user_repository.create_user(
                self._session,
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
            )
            shop = await shop_repository.create_shop(self._session, name=shop_name)
            owner_role = await role_repository.get_owner_role(self._session)
            await membership_repository.create_membership(
                self._session,
                user_id=user.id,
                shop_id=shop.id,
                role_id=owner_role.id,
            )
        except IntegrityError as error:
            # The unique index is the arbiter of two simultaneous registrations of the
            # same address, so this is a 409 rather than a 500.
            await self._session.rollback()
            if "users_email_live" in str(error):
                raise EmailTaken from error
            raise

        result = await issue_session(self._session, self._settings, user, shop.id)
        await self._session.commit()
        return result

    async def login(self, *, email: str, password: str) -> Session:
        """Verify credentials and start a session."""

        user = await user_repository.find_user_by_email(self._session, email)
        if user is None:
            # Burn a verification anyway, so an unknown address costs the same as a
            # known one and response time does not disclose which addresses exist.
            verify_dummy()
            raise InvalidCredentials

        if not verify_password(user.password_hash, password):
            raise InvalidCredentials

        # Only now, with the password proven, is it safe to say more than
        # "credentials are wrong".
        if user.deactivated_at is not None:
            raise AccountDeactivated

        memberships = await membership_repository.list_memberships(
            self._session, user.id
        )
        if not memberships:
            # An account with no live shop cannot do anything, and that is a state
            # worth distinguishing from a bad password.
            raise AccountInactive

        await refresh_token_repository.delete_expired_refresh_tokens(self._session)
        await user_repository.set_last_login(self._session, user.id)
        result = await issue_session(
            self._session, self._settings, user, memberships[0][0].id
        )
        await self._session.commit()
        return result

    async def refresh(self, token: str | None) -> Session:
        """Rotate a refresh token, detecting reuse.

        Reuse means a token that was already rotated has been presented again, which
        is the signature of a stolen value. The response is to revoke the entire
        family, not just the presented row: the legitimate holder has to sign in
        again, and the thief's copy dies with it.
        """

        if not token:
            raise InvalidToken

        stored = await refresh_token_repository.find_refresh_token(
            self._session, utils.hash_refresh_token(token)
        )
        if stored is None:
            raise InvalidToken

        if stored.revoked_at is not None:
            # A revoked token presented again is the signature of a stolen value, so
            # the whole family dies. One exception: if the account was deactivated,
            # that is the real reason and the honest answer. Checking it first keeps
            # the client's error code accurate and avoids logging a reuse alarm for
            # an action the seller took themselves.
            owner = await user_repository.get_user(self._session, stored.user_id)
            if owner is not None and owner.deactivated_at is not None:
                raise AccountInactive

            revoked = await refresh_token_repository.revoke_family(
                self._session, stored.family_id
            )
            await self._session.commit()
            logger.warning(
                "Refresh token reuse detected; revoked %s token(s) in family %s",
                revoked,
                stored.family_id,
            )
            raise InvalidToken

        if stored.expires_at <= datetime.now(UTC):
            raise InvalidToken

        user = await user_repository.get_user(self._session, stored.user_id)
        if user is None:
            raise InvalidToken
        if user.deactivated_at is not None:
            await refresh_token_repository.revoke_all_families_for_user(
                self._session, user.id
            )
            await self._session.commit()
            raise AccountInactive

        if stored.active_shop_id is None:
            raise ShopNotAccessible
        membership = await membership_repository.find_membership(
            self._session, user_id=user.id, shop_id=stored.active_shop_id
        )
        if membership is None or not membership[0].is_active:
            # The bound shop is gone or suspended, so the session cannot continue
            # against it.
            await refresh_token_repository.revoke_family(
                self._session, stored.family_id
            )
            await self._session.commit()
            raise ShopNotAccessible

        family_id = stored.family_id
        await refresh_token_repository.delete_expired_refresh_tokens(self._session)
        result = await issue_session(
            self._session,
            self._settings,
            user,
            stored.active_shop_id,
            family_id=family_id,
        )
        # Mark the presented token replaced only after the new row exists, so
        # ``replaced_by_id`` always points at something.
        newest = await refresh_token_repository.find_refresh_token(
            self._session, utils.hash_refresh_token(result.refresh_token)
        )
        await refresh_token_repository.revoke_refresh_token(
            self._session, stored, newest
        )
        await self._session.commit()
        return result

    async def logout(self, token: str | None) -> None:
        """Revoke the token's whole family.

        Idempotent and silent: a client asking to end its session has nothing to
        learn from a failure, so an absent or unrecognized cookie is not an error.
        """

        if not token:
            return
        stored = await refresh_token_repository.find_refresh_token(
            self._session, utils.hash_refresh_token(token)
        )
        if stored is None:
            return
        await refresh_token_repository.revoke_family(self._session, stored.family_id)
        await self._session.commit()

    async def switch_shop(
        self, *, user_id: uuid.UUID, shop_id: uuid.UUID, refresh_token: str | None
    ) -> Session:
        """Move a session to another shop the caller belongs to.

        The refresh token is rotated as well as the access token, so the session's
        shop is bound server-side. A client cannot assert one shop while holding a
        token issued for another.
        """

        user = await user_repository.get_user(self._session, user_id)
        if user is None:
            raise InvalidToken
        if user.deactivated_at is not None:
            raise AccountInactive

        membership = await membership_repository.find_membership(
            self._session, user_id=user_id, shop_id=shop_id
        )
        if membership is None:
            raise NotAMember
        if not membership[0].is_active:
            raise ShopNotAccessible

        family_id: uuid.UUID | None = None
        if refresh_token:
            stored = await refresh_token_repository.find_refresh_token(
                self._session, utils.hash_refresh_token(refresh_token)
            )
            if stored is not None and stored.revoked_at is None:
                family_id = stored.family_id

        result = await issue_session(
            self._session, self._settings, user, shop_id, family_id=family_id
        )
        if refresh_token and family_id is not None:
            previous = await refresh_token_repository.find_refresh_token(
                self._session, utils.hash_refresh_token(refresh_token)
            )
            newest = await refresh_token_repository.find_refresh_token(
                self._session, utils.hash_refresh_token(result.refresh_token)
            )
            if previous is not None:
                await refresh_token_repository.revoke_refresh_token(
                    self._session, previous, newest
                )
        await self._session.commit()
        return result
