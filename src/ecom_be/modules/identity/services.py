"""Identity use cases.

The service layer decides *what* happens and where a transaction ends. It never
imports FastAPI, never builds a URL, and never touches an HTTP header: cookie
handling is transport and stays in the router, which is what keeps ``SameSite``,
``Path``, and ``Secure`` in one place instead of threaded through a use case.

Two rules are load-bearing:

* Services return schema-shaped results, never ORM objects. The contract is the
  boundary, and passing an ORM object out is how a lazy load ends up in a response.
* A service commits. Repositories never do, so a multi-step use case can be atomic:
  ``register`` writes a user, a shop, and a membership in one transaction and
  commits once, which is why a failure cannot leave a user with no shop.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.core.config import Settings, get_settings
from ecom_be.infrastructure.security.passwords import (
    hash_password,
    verify_dummy,
    verify_password,
)
from ecom_be.modules.identity import repository, utils
from ecom_be.modules.identity.constants import UPLOAD_FIELD_NAME
from ecom_be.modules.identity.errors import (
    AccountDeactivated,
    AccountInactive,
    ConfirmationMismatch,
    EmailTaken,
    InvalidCredentials,
    InvalidToken,
    NotAMember,
    RateLimited,
    ShopNotAccessible,
)
from ecom_be.modules.identity.models import Role, Shop, User

logger = logging.getLogger(__name__)

# Rate-limit windows. Registration is the tightest because it is the endpoint that
# discloses whether an address is taken.
REGISTER_LIMIT = 5
REGISTER_WINDOW_SECONDS = 3600
LOGIN_LIMIT = 10
LOGIN_WINDOW_SECONDS = 900
UPLOAD_LIMIT = 30
UPLOAD_WINDOW_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class Session:
    """What a successful sign-in produces.

    ``refresh_token`` is a field here and nowhere else on the way out: the router
    turns it into an httpOnly cookie and nothing else ever sees it.
    """

    access_token: str
    expires_in: int
    user: User
    active_shop: Shop
    memberships: list[tuple[Shop, Role]]
    permissions: list[str]
    refresh_token: str


class RateLimitStore(Protocol):
    """The two Redis commands the limiter needs.

    Narrowing the dependency to what is used is what lets the failure path be tested
    with a small fake instead of a real server, and it keeps the limiter from
    acquiring a reason to reach for anything else.
    """

    async def incr(self, key: str) -> int: ...

    async def expire(self, key: str, seconds: int) -> bool: ...


async def enforce_rate_limit(
    client: RateLimitStore | None,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Refuse an attempt past the limit. A Redis failure lets it through.

    Failing closed would turn a cache outage into a total sign-in outage, which is a
    worse outcome than a temporarily unthrottled login. The event is logged so the
    degradation is visible rather than silent.
    """

    if client is None:
        return
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
        if count > limit:
            raise RateLimited
    except RateLimited:
        raise
    except Exception:  # noqa: BLE001 - a cache outage must not deny sign-in
        logger.warning("Rate limit check failed for %s; allowing the request", key)


class IdentityService:
    """Use cases for accounts, sessions, and shops."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings if settings is not None else get_settings()

    # -- registration and sign-in ------------------------------------------------

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

        if await repository.find_user_by_email(self._session, email) is not None:
            raise EmailTaken

        try:
            user = await repository.create_user(
                self._session,
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
            )
            shop = await repository.create_shop(self._session, name=shop_name)
            owner_role = await repository.get_owner_role(self._session)
            await repository.create_membership(
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

        result = await self._issue_session(user, shop.id)
        await self._session.commit()
        return result

    async def login(self, *, email: str, password: str) -> Session:
        """Verify credentials and start a session."""

        user = await repository.find_user_by_email(self._session, email)
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

        memberships = await repository.list_memberships(self._session, user.id)
        if not memberships:
            # An account with no live shop cannot do anything, and that is a state
            # worth distinguishing from a bad password.
            raise AccountInactive

        await repository.delete_expired_refresh_tokens(self._session)
        await repository.set_last_login(self._session, user.id)
        result = await self._issue_session(user, memberships[0][0].id)
        await self._session.commit()
        return result

    # -- session lifecycle -------------------------------------------------------

    async def refresh(self, token: str | None) -> Session:
        """Rotate a refresh token, detecting reuse.

        Reuse means a token that was already rotated has been presented again, which
        is the signature of a stolen value. The response is to revoke the entire
        family, not just the presented row: the legitimate holder has to sign in
        again, and the thief's copy dies with it.
        """

        if not token:
            raise InvalidToken

        stored = await repository.find_refresh_token(
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
            owner = await repository.get_user(self._session, stored.user_id)
            if owner is not None and owner.deactivated_at is not None:
                raise AccountInactive

            revoked = await repository.revoke_family(self._session, stored.family_id)
            await self._session.commit()
            logger.warning(
                "Refresh token reuse detected; revoked %s token(s) in family %s",
                revoked,
                stored.family_id,
            )
            raise InvalidToken

        if stored.expires_at <= datetime.now(UTC):
            raise InvalidToken

        user = await repository.get_user(self._session, stored.user_id)
        if user is None:
            raise InvalidToken
        if user.deactivated_at is not None:
            await repository.revoke_all_families_for_user(self._session, user.id)
            await self._session.commit()
            raise AccountInactive

        if stored.active_shop_id is None:
            raise ShopNotAccessible
        membership = await repository.find_membership(
            self._session, user_id=user.id, shop_id=stored.active_shop_id
        )
        if membership is None or not membership[0].is_active:
            # The bound shop is gone or suspended, so the session cannot continue
            # against it.
            await repository.revoke_family(self._session, stored.family_id)
            await self._session.commit()
            raise ShopNotAccessible

        family_id = stored.family_id
        await repository.delete_expired_refresh_tokens(self._session)
        result = await self._issue_session(
            user, stored.active_shop_id, family_id=family_id
        )
        # Mark the presented token replaced only after the new row exists, so
        # ``replaced_by_id`` always points at something.
        newest = await repository.find_refresh_token(
            self._session, utils.hash_refresh_token(result.refresh_token)
        )
        await repository.revoke_refresh_token(self._session, stored, newest)
        await self._session.commit()
        return result

    async def logout(self, token: str | None) -> None:
        """Revoke the token's whole family.

        Idempotent and silent: a client asking to end its session has nothing to
        learn from a failure, so an absent or unrecognized cookie is not an error.
        """

        if not token:
            return
        stored = await repository.find_refresh_token(
            self._session, utils.hash_refresh_token(token)
        )
        if stored is None:
            return
        await repository.revoke_family(self._session, stored.family_id)
        await self._session.commit()

    async def switch_shop(
        self, *, user_id: uuid.UUID, shop_id: uuid.UUID, refresh_token: str | None
    ) -> Session:
        """Move a session to another shop the caller belongs to.

        The refresh token is rotated as well as the access token, so the session's
        shop is bound server-side. A client cannot assert one shop while holding a
        token issued for another.
        """

        user = await repository.get_user(self._session, user_id)
        if user is None:
            raise InvalidToken
        if user.deactivated_at is not None:
            raise AccountInactive

        membership = await repository.find_membership(
            self._session, user_id=user_id, shop_id=shop_id
        )
        if membership is None:
            raise NotAMember
        if not membership[0].is_active:
            raise ShopNotAccessible

        family_id: uuid.UUID | None = None
        if refresh_token:
            stored = await repository.find_refresh_token(
                self._session, utils.hash_refresh_token(refresh_token)
            )
            if stored is not None and stored.revoked_at is None:
                family_id = stored.family_id

        result = await self._issue_session(user, shop_id, family_id=family_id)
        if refresh_token and family_id is not None:
            previous = await repository.find_refresh_token(
                self._session, utils.hash_refresh_token(refresh_token)
            )
            newest = await repository.find_refresh_token(
                self._session, utils.hash_refresh_token(result.refresh_token)
            )
            if previous is not None:
                await repository.revoke_refresh_token(self._session, previous, newest)
        await self._session.commit()
        return result

    # -- profile -----------------------------------------------------------------

    async def me(
        self, *, user_id: uuid.UUID, shop_id: uuid.UUID
    ) -> tuple[User, Shop, list[tuple[Shop, Role]], list[str]]:
        """The caller's identity, their memberships, and their effective permissions."""

        resolved = await repository.effective_permissions(
            self._session, user_id=user_id, shop_id=shop_id
        )
        if resolved is None:
            # Distinguish "the account is gone" from "the shop is not yours", so a
            # deactivated client stops retrying instead of looping on a 401.
            user = await repository.get_user(self._session, user_id)
            if user is None or user.deactivated_at is not None:
                raise AccountInactive
            raise ShopNotAccessible

        user, _role, permissions = resolved
        shop = await repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        memberships = await repository.list_memberships(self._session, user_id)
        return user, shop, memberships, permissions

    async def update_profile(
        self, *, user_id: uuid.UUID, changes: dict[str, str | None]
    ) -> User:
        """Apply only the supplied keys, so an omitted field is left alone."""

        user = await repository.get_user(self._session, user_id)
        if user is None:
            raise AccountInactive
        await repository.update_user_profile(self._session, user, changes)
        await self._session.commit()
        return user

    async def set_avatar(self, *, user_id: uuid.UUID, key: str | None) -> User:
        user = await repository.get_user(self._session, user_id)
        if user is None:
            raise AccountInactive
        await repository.set_user_avatar_key(self._session, user, key)
        await self._session.commit()
        return user

    async def get_user(self, user_id: uuid.UUID) -> User:
        """The account, for a route that has already authorized the caller."""

        user = await repository.get_user(self._session, user_id)
        if user is None:
            raise AccountInactive
        return user

    # -- deactivation ------------------------------------------------------------

    async def deactivate(self, *, user_id: uuid.UUID, password: str) -> None:
        """Retire an account, confirmed by its password.

        One-way: it sets ``deactivated_at`` and revokes every session, and it does
        *not* set ``deleted_at``. That distinction is what keeps the email reserved,
        because the seller may return.
        """

        user = await repository.get_user(self._session, user_id)
        if user is None:
            raise AccountInactive
        if not verify_password(user.password_hash, password):
            raise InvalidCredentials

        await repository.deactivate_user(self._session, user)
        await repository.revoke_all_families_for_user(self._session, user.id)
        await self._session.commit()

    # -- shops -------------------------------------------------------------------

    async def update_active_shop(
        self, *, shop_id: uuid.UUID, changes: dict[str, str | None]
    ) -> Shop:
        """Apply profile changes to the active shop. ``slug`` is never among them."""

        shop = await repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        await repository.update_shop_profile(self._session, shop, changes)
        await self._session.commit()
        return shop

    async def set_shop_background(self, *, shop_id: uuid.UUID, key: str | None) -> Shop:
        shop = await repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        await repository.set_shop_background_key(self._session, shop, key)
        await self._session.commit()
        return shop

    async def delete_active_shop(
        self, *, shop_id: uuid.UUID, confirm_shop_name: str
    ) -> None:
        """Retire a shop, its memberships, and the sessions bound to it.

        Confirmed by the shop's own name, read from the database rather than trusted
        from the request: a dialog any click can dismiss is not a guard.

        Nothing is purged. Hard deletion needs a cascade policy for orders, and
        orders do not exist yet.
        """

        shop = await repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        if shop.name != confirm_shop_name:
            raise ConfirmationMismatch

        await repository.soft_delete_memberships_for_shop(self._session, shop.id)
        await repository.soft_delete_shop(self._session, shop)
        revoked = await repository.revoke_families_for_shop(self._session, shop.id)
        await self._session.commit()
        logger.info("Shop %s deleted; revoked %s session(s)", shop.id, revoked)

    async def active_shop(self, shop_id: uuid.UUID) -> Shop:
        shop = await repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        return shop

    async def shop_for_principal(self, shop_id: uuid.UUID) -> Shop:
        """Alias kept meaningful at the call site: the route passes a token claim."""

        return await self.active_shop(shop_id)

    # -- internals ---------------------------------------------------------------

    async def _issue_session(
        self,
        user: User,
        shop_id: uuid.UUID,
        *,
        family_id: uuid.UUID | None = None,
    ) -> Session:
        """Mint an access token, persist the refresh row, and assemble the result.

        Does not commit: the caller decides the transaction boundary, which is what
        lets ``register`` keep four writes in one transaction.
        """

        membership = await repository.find_membership(
            self._session, user_id=user.id, shop_id=shop_id
        )
        if membership is None:
            raise NotAMember
        shop, _role = membership

        resolved = await repository.effective_permissions(
            self._session, user_id=user.id, shop_id=shop_id
        )
        permissions = resolved[2] if resolved is not None else []

        access_token = utils.issue_access_token(
            self._settings, user_id=str(user.id), active_shop_id=str(shop_id)
        )
        raw_refresh, digest = utils.new_refresh_token()
        await repository.create_refresh_token(
            self._session,
            user_id=user.id,
            active_shop_id=shop_id,
            token_hash=digest,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=self._settings.refresh_token_ttl_seconds),
            family_id=family_id,
        )
        memberships = await repository.list_memberships(self._session, user.id)
        return Session(
            access_token=access_token,
            expires_in=self._settings.access_token_ttl_seconds,
            user=user,
            active_shop=shop,
            memberships=memberships,
            permissions=permissions,
            refresh_token=raw_refresh,
        )


__all__ = [
    "LOGIN_LIMIT",
    "LOGIN_WINDOW_SECONDS",
    "REGISTER_LIMIT",
    "REGISTER_WINDOW_SECONDS",
    "UPLOAD_FIELD_NAME",
    "UPLOAD_LIMIT",
    "UPLOAD_WINDOW_SECONDS",
    "IdentityService",
    "Session",
    "enforce_rate_limit",
]
