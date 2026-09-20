"""Use cases for the active shop: its profile, its background, and its retirement."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.errors.identity import ConfirmationMismatch, ShopNotAccessible
from app.models.identity import Shop
from app.repositories import (
    membership_repository,
    refresh_token_repository,
    shop_repository,
)

logger = logging.getLogger(__name__)


class ShopService:
    """One shop's own profile, background, and lifecycle."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings if settings is not None else get_settings()

    async def update_active_shop(
        self, *, shop_id: uuid.UUID, changes: dict[str, str | None]
    ) -> Shop:
        """Apply profile changes to the active shop. ``slug`` is never among them."""

        shop = await shop_repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        await shop_repository.update_shop_profile(self._session, shop, changes)
        await self._session.commit()
        return shop

    async def set_shop_background(self, *, shop_id: uuid.UUID, key: str | None) -> Shop:
        shop = await shop_repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        await shop_repository.set_shop_background_key(self._session, shop, key)
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

        shop = await shop_repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        if shop.name != confirm_shop_name:
            raise ConfirmationMismatch

        await membership_repository.soft_delete_memberships_for_shop(
            self._session, shop.id
        )
        await shop_repository.soft_delete_shop(self._session, shop)
        revoked = await refresh_token_repository.revoke_families_for_shop(
            self._session, shop.id
        )
        await self._session.commit()
        logger.info("Shop %s deleted; revoked %s session(s)", shop.id, revoked)

    async def active_shop(self, shop_id: uuid.UUID) -> Shop:
        shop = await shop_repository.get_shop(self._session, shop_id)
        if shop is None:
            raise ShopNotAccessible
        return shop

    async def shop_for_principal(self, shop_id: uuid.UUID) -> Shop:
        """Alias kept meaningful at the call site: the route passes a token claim."""

        return await self.active_shop(shop_id)
