"""The caller's own account: read, partial update, avatar, and deactivation."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.errors.identity import (
    AccountInactive,
    InvalidCredentials,
    ShopNotAccessible,
)
from app.infrastructure.security.passwords import verify_password
from app.models.identity import Role, Shop, User
from app.repositories import (
    membership_repository,
    refresh_token_repository,
    shop_repository,
    user_repository,
)


class AccountService:
    """One account's own profile, avatar, and lifecycle."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings if settings is not None else get_settings()

    async def me(
        self, *, user_id: uuid.UUID, shop_id: uuid.UUID
    ) -> tuple[User, Shop, list[tuple[Shop, Role]], list[str]]:
        """The caller's identity, their memberships, and their effective permissions."""

        resolved = await membership_repository.effective_permissions(
            self._session, user_id=user_id, shop_id=shop_id
        )
        if resolved is None:
            # Distinguish "the account is gone" from "the shop is not yours", so a
            # deactivated client stops retrying instead of looping on a 401.
            user = await user_repository.get_user(self._session, user_id)
            if user is None or user.deactivated_at is not None:
                raise AccountInactive
            raise ShopNotAccessible

        user, _role, permissions = resolved
        shop = await shop_repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        memberships = await membership_repository.list_memberships(
            self._session, user_id
        )
        return user, shop, memberships, permissions

    async def update_profile(
        self, *, user_id: uuid.UUID, changes: dict[str, str | None]
    ) -> User:
        """Apply only the supplied keys, so an omitted field is left alone."""

        user = await user_repository.get_user(self._session, user_id)
        if user is None:
            raise AccountInactive
        await user_repository.update_user_profile(self._session, user, changes)
        await self._session.commit()
        return user

    async def set_avatar(self, *, user_id: uuid.UUID, key: str | None) -> User:
        user = await user_repository.get_user(self._session, user_id)
        if user is None:
            raise AccountInactive
        await user_repository.set_user_avatar_key(self._session, user, key)
        await self._session.commit()
        return user

    async def get_user(self, user_id: uuid.UUID) -> User:
        """The account, for a route that has already authorized the caller."""

        user = await user_repository.get_user(self._session, user_id)
        if user is None:
            raise AccountInactive
        return user

    async def deactivate(self, *, user_id: uuid.UUID, password: str) -> None:
        """Retire an account, confirmed by its password.

        One-way: it sets ``deactivated_at`` and revokes every session, and it does
        *not* set ``deleted_at``. That distinction is what keeps the email reserved,
        because the seller may return.
        """

        user = await user_repository.get_user(self._session, user_id)
        if user is None:
            raise AccountInactive
        if not verify_password(user.password_hash, password):
            raise InvalidCredentials

        await user_repository.deactivate_user(self._session, user)
        await refresh_token_repository.revoke_all_families_for_user(
            self._session, user.id
        )
        await self._session.commit()
