"""Contract: the local storage adapter.

The traversal guard is the reason to test this at all. Everything else is a thin
filesystem call; the guard is the piece where a mistake means a request can write
outside the storage root.
"""

from __future__ import annotations

import pytest

from app.infrastructure.storage.local import LocalStorageBackend

pytestmark = pytest.mark.anyio

KEY = "avatars/11111111-1111-4111-8111-111111111111/abc.webp"
PAYLOAD = b"normalized webp bytes"


@pytest.fixture
def backend(tmp_path) -> LocalStorageBackend:
    return LocalStorageBackend(root=tmp_path / "media")


class TestRoundTrip:
    async def test_put_then_read_returns_the_same_bytes(self, backend):
        await backend.put(KEY, PAYLOAD, "image/webp")

        assert await backend.read(KEY) == PAYLOAD

    async def test_put_creates_parent_directories(self, backend):
        await backend.put("deep/nested/path/object.webp", PAYLOAD, "image/webp")

        assert await backend.read("deep/nested/path/object.webp") == PAYLOAD

    async def test_reading_an_absent_key_returns_none(self, backend):
        assert await backend.read("avatars/nobody/absent.webp") is None

    async def test_deleting_an_absent_key_is_silent(self, backend):
        """Deleting an avatar that is already gone must not be an error."""

        await backend.delete("avatars/nobody/absent.webp")

    async def test_delete_removes_the_object(self, backend):
        await backend.put(KEY, PAYLOAD, "image/webp")

        await backend.delete(KEY)

        assert await backend.read(KEY) is None

    async def test_deleting_twice_is_silent(self, backend):
        await backend.put(KEY, PAYLOAD, "image/webp")

        await backend.delete(KEY)
        await backend.delete(KEY)

        assert await backend.read(KEY) is None

    async def test_a_repeated_put_is_idempotent(self, backend):
        """The key is a content digest, so the same key always means the same bytes."""

        await backend.put(KEY, PAYLOAD, "image/webp")
        await backend.put(KEY, PAYLOAD, "image/webp")

        assert await backend.read(KEY) == PAYLOAD


class TestTraversalGuard:
    @pytest.mark.parametrize(
        "key",
        [
            "../escape.webp",
            "avatars/../../escape.webp",
            "..",
            "avatars/..",
        ],
    )
    async def test_a_parent_traversal_key_is_refused(self, backend, key):
        with pytest.raises(ValueError):
            await backend.put(key, PAYLOAD, "image/webp")

    @pytest.mark.parametrize("key", ["/absolute.webp", "/etc/passwd"])
    async def test_an_absolute_key_is_refused(self, backend, key):
        with pytest.raises(ValueError):
            await backend.put(key, PAYLOAD, "image/webp")

    async def test_an_empty_key_is_refused(self, backend):
        with pytest.raises(ValueError):
            await backend.put("", PAYLOAD, "image/webp")

    async def test_the_guard_also_applies_to_reads_and_deletes(self, backend):
        for operation in (backend.read, backend.delete):
            with pytest.raises(ValueError):
                await operation("../escape.webp")

    async def test_a_refused_key_writes_nothing_outside_the_root(
        self, backend, tmp_path
    ):
        with pytest.raises(ValueError):
            await backend.put("../escaped.webp", PAYLOAD, "image/webp")

        assert not (tmp_path / "escaped.webp").exists()

    async def test_a_key_that_merely_contains_dots_is_not_a_traversal(self, backend):
        """``..`` as a path *segment* is the danger, not two dots in a name."""

        await backend.put("avatars/..hidden.webp", PAYLOAD, "image/webp")

        assert await backend.read("avatars/..hidden.webp") == PAYLOAD
