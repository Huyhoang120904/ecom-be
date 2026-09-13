"""Derive media URLs from stored object keys.

The database holds an object key such as ``avatars/<user-id>/<digest>.webp``, never a
URL. A stored absolute URL would bake the deployment host into every row and break
the moment the API moved, so the URL is built per response from the request's own
origin, or from ``MEDIA_BASE_URL`` when one is configured.

This lives in ``api/`` because it is a transport concern shared by two modules
(identity renders them, media serves them), and because both modules need the same
answer to "what is this object's URL" without either importing the other's
internals.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Request

from ecom_be.modules.identity.models import Shop, User

AVATAR_PATH = "/api/v1/media/avatar"
BACKGROUND_PATH = "/api/v1/media/shop-background"


def _origin(request: Request) -> str:
    """The absolute origin to build media URLs from."""

    settings = request.app.state.settings
    if settings.media_base_url:
        return str(settings.media_base_url).rstrip("/")
    return str(request.base_url).rstrip("/")


def _version(stamp: datetime | None) -> str:
    """A cache-busting version for a derived URL.

    Without it, replacing an avatar would keep serving the cached old image, because
    the URL is keyed by the entity id rather than the content.
    """

    return str(int(stamp.timestamp())) if stamp is not None else "0"


def avatar_url(user: User, request: Request) -> str | None:
    """The URL for an account's avatar, or ``None`` when it has none."""

    if not user.avatar_key:
        return None
    stamp = _version(user.avatar_updated_at)
    return f"{_origin(request)}{AVATAR_PATH}/{user.id}.webp?v={stamp}"


def background_url(shop: Shop, request: Request) -> str | None:
    """The URL for a shop's background, or ``None`` when it has none."""

    if not shop.background_key:
        return None
    return (
        f"{_origin(request)}{BACKGROUND_PATH}/{shop.id}.webp"
        f"?v={_version(shop.background_updated_at)}"
    )
