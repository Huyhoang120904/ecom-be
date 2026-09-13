"""The media HTTP surface: two public read routes.

They are public and read-only, which is a decision rather than an oversight. An
avatar and a shop background are shareable-by-intent images: both paths are keyed by
a UUID disclosed only to people who already hold a token, the response carries a long
cache lifetime and an ``ETag``, and neither image is secret. A signed URL would need
a signing key and a TTL for no real gain here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.api.deps import get_application_db_session
from ecom_be.errors.media import ImageNotFound
from ecom_be.infrastructure.storage.local import LocalStorageBackend, StorageBackend
from ecom_be.repositories import identity as repository
from ecom_be.services.media import MediaService

router = APIRouter(prefix="/api/v1/media", tags=["media"])

WEBP = "image/webp"
# A year: the URL is versioned by a query parameter when the image is replaced, so a
# stale cache is impossible and a long lifetime is safe.
CACHE_SECONDS = 31_536_000


def get_storage(request: Request) -> StorageBackend:
    """The storage backend owned by the application lifecycle."""

    backend = getattr(request.app.state, "storage", None)
    if backend is None:
        backend = LocalStorageBackend(root=request.app.state.settings.media_root)
        request.app.state.storage = backend
    return backend


def get_media_service(
    request: Request,
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> MediaService:
    return MediaService(storage, request.app.state.settings)


def _serve(payload: bytes, etag: str, request: Request) -> Response:
    """Return the image, or a 304 when the client already has this version."""

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    return Response(
        content=payload,
        media_type=WEBP,
        headers={
            "etag": etag,
            "cache-control": f"public, max-age={CACHE_SECONDS}, immutable",
        },
    )


@router.get("/avatar/{user_id}.webp")
async def serve_avatar(
    user_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    media: Annotated[MediaService, Depends(get_media_service)],
) -> Response:
    """Serve an account's avatar.

    The stored key is read from the database rather than reconstructed from the
    request, so a client cannot ask for an object the account does not own, and a
    deleted avatar is a 404 rather than a stale hit.
    """

    user = await repository.get_user(session, user_id)
    if user is None or not user.avatar_key:
        raise ImageNotFound

    result = await media.read(user.avatar_key)
    if result is None:
        raise ImageNotFound
    payload, digest = result
    return _serve(payload, f'"{digest}"', request)


@router.get("/shop-background/{shop_id}.webp")
async def serve_shop_background(
    shop_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    media: Annotated[MediaService, Depends(get_media_service)],
) -> Response:
    shop = await repository.get_shop(session, shop_id)
    if shop is None or not shop.background_key:
        raise ImageNotFound

    result = await media.read(shop.background_key)
    if result is None:
        raise ImageNotFound
    payload, digest = result
    return _serve(payload, f'"{digest}"', request)
