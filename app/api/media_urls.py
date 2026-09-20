"""Derive media URLs from stored object keys.

The database holds an object key such as ``avatars/<user-id>/<digest>.webp``, never a
URL. A stored absolute URL would bake the deployment host into every row and break
the moment the API moved, so the URL is built per response from the request's own
origin, or from ``MEDIA_BASE_URL`` when one is configured.

The cache-busting version is the *content digest* taken from the key, not a
timestamp. A timestamp has second resolution, so two uploads within one second would
produce the same URL and a cache would keep serving the first image; the digest
changes whenever the bytes change, which is exactly the condition a cache needs.

This lives in ``api/`` because it is a transport concern shared by two modules
(identity renders these URLs, media serves them), and because both need the same
answer to "what is this object's URL" without either importing the other's
internals.
"""

from __future__ import annotations

from fastapi import Request

from app.models.identity import Shop, User

AVATAR_PATH = "/api/v1/media/avatar"
BACKGROUND_PATH = "/api/v1/media/shop-background"

_DIGEST_LENGTH = 64


def _origin(request: Request) -> str:
    """The absolute origin to build media URLs from."""

    settings = request.app.state.settings
    if settings.media_base_url:
        return str(settings.media_base_url).rstrip("/")
    return str(request.base_url).rstrip("/")


def _version(key: str) -> str:
    """The content digest embedded in a storage key, or ``"0"`` if it is not one.

    Falls back rather than raising: a URL that lacks a version is a cache that may
    revalidate too eagerly, which is a far better failure than a response that cannot
    be built at all.
    """

    stem = key.rsplit("/", 1)[-1].removesuffix(".webp")
    return stem if len(stem) == _DIGEST_LENGTH else "0"


def avatar_url(user: User, request: Request) -> str | None:
    """The URL for an account's avatar, or ``None`` when it has none."""

    if not user.avatar_key:
        return None
    return (
        f"{_origin(request)}{AVATAR_PATH}/{user.id}.webp?v={_version(user.avatar_key)}"
    )


def background_url(shop: Shop, request: Request) -> str | None:
    """The URL for a shop's background, or ``None`` when it has none."""

    if not shop.background_key:
        return None
    return (
        f"{_origin(request)}{BACKGROUND_PATH}/{shop.id}.webp"
        f"?v={_version(shop.background_key)}"
    )
