"""The identity HTTP contract, assembled from one router per resource area.

``router`` carries the auth surface (registration, sign-in, the caller's own
profile and avatar) and ``shops_router`` the active-shop surface. ``api/v1``
includes both; nothing else imports these.
"""

from __future__ import annotations

from fastapi import APIRouter

from ecom_be.api.v1.identity import auth, media_uploads, profile, shops
from ecom_be.api.v1.identity.common import REFRESH_COOKIE, REFRESH_COOKIE_PATH

router = APIRouter()
for _part in (auth.router, profile.router, media_uploads.router):
    router.include_router(_part)

shops_router: APIRouter = shops.shops_router

__all__ = ["REFRESH_COOKIE", "REFRESH_COOKIE_PATH", "router", "shops_router"]
