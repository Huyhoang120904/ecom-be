"""Media use cases: store, delete, resolve.

The key layout lives here and nowhere else, so storage keys never become part of a
contract and a future object-storage adapter changes this file rather than its
callers.

The identity and shop modules call ``store_avatar`` / ``store_background`` and
persist the returned key. They never learn how the bytes are validated, and this
module never learns which entity owns the key.
"""

from __future__ import annotations

import uuid

from ecom_be.config.settings import Settings, get_settings
from ecom_be.infrastructure.storage.local import StorageBackend
from ecom_be.utils import media as utils

AVATAR_PREFIX = "avatars"
BACKGROUND_PREFIX = "shop-backgrounds"


class MediaService:
    def __init__(
        self,
        storage: StorageBackend,
        settings: Settings | None = None,
    ) -> None:
        self._storage = storage
        self._settings = settings if settings is not None else get_settings()

    # -- keys --------------------------------------------------------------------

    @staticmethod
    def avatar_key(user_id: uuid.UUID, digest: str) -> str:
        """``avatars/<user>/<digest>.webp``.

        Keyed by the owner so the prefix groups one account's objects, and by the
        content digest so a byte-identical re-upload lands on the same key instead of
        accumulating duplicates.
        """

        return f"{AVATAR_PREFIX}/{user_id}/{digest}.webp"

    @staticmethod
    def background_key(shop_id: uuid.UUID, digest: str) -> str:
        return f"{BACKGROUND_PREFIX}/{shop_id}/{digest}.webp"

    # -- use cases ---------------------------------------------------------------

    async def store_avatar(
        self, *, user_id: uuid.UUID, image_bytes: bytes, declared_content_type: str
    ) -> str:
        """Normalize and store an avatar, returning its storage key."""

        payload, digest = utils.normalize_avatar(
            image_bytes,
            declared_content_type=declared_content_type,
            max_bytes=self._settings.max_upload_bytes,
        )
        key = self.avatar_key(user_id, digest)
        await self._storage.put(key, payload, "image/webp")
        return key

    async def store_background(
        self, *, shop_id: uuid.UUID, image_bytes: bytes, declared_content_type: str
    ) -> str:
        """Normalize and store a shop background, returning its storage key."""

        payload, digest = utils.normalize_background(
            image_bytes,
            declared_content_type=declared_content_type,
            max_bytes=self._settings.max_upload_bytes,
        )
        key = self.background_key(shop_id, digest)
        await self._storage.put(key, payload, "image/webp")
        return key

    async def delete(self, key: str | None) -> None:
        """Remove an object. An absent key is not an error.

        Deleting an avatar that is already gone must be a no-op rather than a
        failure: the caller is asking for a state, and that state already holds.
        """

        if key:
            await self._storage.delete(key)

    async def read(self, key: str) -> tuple[bytes, str] | None:
        """Read an object and its ETag. Returns ``None`` when it is absent."""

        payload = await self._storage.read(key)
        if payload is None:
            return None
        return payload, utils.content_digest(payload)
