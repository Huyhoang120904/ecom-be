"""Storage adapters behind one protocol.

``StorageBackend`` is the single swap point between a local filesystem and object
storage. Everything above it — the service, the routes, the identity module —
depends on the protocol, so replacing the adapter is a change to one file and one
setting, not a change to any caller.
"""

from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath
from typing import Protocol


class StorageBackend(Protocol):
    """Where normalized image bytes live."""

    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def read(self, key: str) -> bytes | None: ...


class LocalStorageBackend:
    """A filesystem adapter rooted at one directory.

    Keys are relative POSIX paths under the root. The traversal guard is the reason
    this class exists rather than a bare ``write_bytes`` call: a key that escapes the
    root is how a path traversal starts, and the check belongs where the write
    happens rather than at every call site.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def _resolve(self, key: str) -> Path:
        if not key:
            raise ValueError("storage key must not be empty")
        if key.startswith("/") or ".." in PurePosixPath(key).parts:
            raise ValueError("storage key must be a relative path inside the root")

        resolved = (self._root / key).resolve()
        root = self._root.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError("storage key escapes the storage root")
        return resolved

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Write the object.

        ``content_type`` is accepted and deliberately unused: a local file has no
        metadata to carry it, and the serving route already knows the type from the
        key. The parameter stays in the protocol because object storage needs it, and
        a caller should not have to know which adapter it holds.
        """

        del content_type
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # A byte-identical re-upload writes the same bytes to the same path, so it is
        # a no-op rather than a duplicate object.
        await asyncio.to_thread(path.write_bytes, data)

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        await asyncio.to_thread(path.unlink, True)

    async def read(self, key: str) -> bytes | None:
        path = self._resolve(key)
        if not await asyncio.to_thread(path.is_file):
            return None
        return await asyncio.to_thread(path.read_bytes)
