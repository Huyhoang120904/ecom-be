"""Identity use cases, split by seam behind one entry point.

``IdentityService`` composes the three seams so a caller keeps a single object:
``AuthService`` owns credentials and sessions, ``AccountService`` owns the caller's own
profile, and ``ShopService`` owns the active shop. All three run against the same
request-scoped session, so a use case that crosses seams still shares one transaction.

Reach for a seam directly when a caller genuinely needs only that seam; the composite
exists so the HTTP layer does not have to know which seam a route lands in.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.config.settings import Settings, get_settings
from ecom_be.models.identity import Role, Shop, User
from ecom_be.services.account_service import AccountService
from ecom_be.services.auth_service import AuthService
from ecom_be.services.session_service import Session
from ecom_be.services.shop_service import ShopService

__all__ = [
    "AccountService",
    "AuthService",
    "IdentityService",
    "Session",
    "ShopService",
]


class IdentityService:
    """Every identity use case, delegating to the seam that owns it."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings if settings is not None else get_settings()

    def _auth(self) -> AuthService:
        return AuthService(self._session, self._settings)

    def _account(self) -> AccountService:
        return AccountService(self._session, self._settings)

    def _shop(self) -> ShopService:
        return ShopService(self._session, self._settings)

    # -- authentication ----------------------------------------------------------

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        shop_name: str,
    ) -> Session:
        return await self._auth().register(
            email=email,
            password=password,
            full_name=full_name,
            shop_name=shop_name,
        )

    async def login(self, *, email: str, password: str) -> Session:
        return await self._auth().login(email=email, password=password)

    async def refresh(self, token: str | None) -> Session:
        return await self._auth().refresh(token)

    async def logout(self, token: str | None) -> None:
        await self._auth().logout(token)

    async def switch_shop(
        self, *, user_id: uuid.UUID, shop_id: uuid.UUID, refresh_token: str | None
    ) -> Session:
        return await self._auth().switch_shop(
            user_id=user_id, shop_id=shop_id, refresh_token=refresh_token
        )

    # -- the caller's own account ------------------------------------------------

    async def me(
        self, *, user_id: uuid.UUID, shop_id: uuid.UUID
    ) -> tuple[User, Shop, list[tuple[Shop, Role]], list[str]]:
        return await self._account().me(user_id=user_id, shop_id=shop_id)

    async def update_profile(
        self, *, user_id: uuid.UUID, changes: dict[str, str | None]
    ) -> User:
        return await self._account().update_profile(user_id=user_id, changes=changes)

    async def set_avatar(self, *, user_id: uuid.UUID, key: str | None) -> User:
        return await self._account().set_avatar(user_id=user_id, key=key)

    async def get_user(self, user_id: uuid.UUID) -> User:
        return await self._account().get_user(user_id)

    async def deactivate(self, *, user_id: uuid.UUID, password: str) -> None:
        await self._account().deactivate(user_id=user_id, password=password)

    # -- the active shop ---------------------------------------------------------

    async def update_active_shop(
        self, *, shop_id: uuid.UUID, changes: dict[str, str | None]
    ) -> Shop:
        return await self._shop().update_active_shop(shop_id=shop_id, changes=changes)

    async def set_shop_background(self, *, shop_id: uuid.UUID, key: str | None) -> Shop:
        return await self._shop().set_shop_background(shop_id=shop_id, key=key)

    async def delete_active_shop(
        self, *, shop_id: uuid.UUID, confirm_shop_name: str
    ) -> None:
        await self._shop().delete_active_shop(
            shop_id=shop_id, confirm_shop_name=confirm_shop_name
        )

    async def active_shop(self, shop_id: uuid.UUID) -> Shop:
        return await self._shop().active_shop(shop_id)

    async def shop_for_principal(self, shop_id: uuid.UUID) -> Shop:
        return await self._shop().shop_for_principal(shop_id)
