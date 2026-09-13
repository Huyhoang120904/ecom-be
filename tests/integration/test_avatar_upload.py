"""Contract: avatar and shop-background upload, serving, and isolation.

Marked ``db`` because the stored key lives on a database row, and the serving route
reads that row rather than reconstructing a path from the request.
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from PIL import Image

pytestmark = [pytest.mark.anyio, pytest.mark.db]

PASSWORD = "a-perfectly-fine-password"


def png(
    size: tuple[int, int] = (600, 600), colour: tuple[int, int, int] = (90, 40, 10)
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg(size: tuple[int, int] = (800, 450)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 90, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


async def signed_up(client: AsyncClient, email: str) -> dict[str, str]:
    """Register and return an access-token header."""

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": "Upload Person",
            "shop_name": f"{email.split('@')[0].replace('.', ' ').title()} Shop",
        },
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return {"authorization": f"Bearer {login.json()['data']['access_token']}"}


def fetch_path(url: str) -> str:
    """The path a returned absolute media URL points at, for an in-process client."""

    return url.split("://", 1)[1].split("/", 1)[1].split("?", 1)[0]


class TestAvatarUpload:
    async def test_uploading_returns_a_url_that_serves_a_512_webp(
        self, db_async_client
    ):
        headers = await signed_up(db_async_client, "avatar@example.com")

        upload = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("me.png", png(), "image/png")},
            headers=headers,
        )

        assert upload.status_code == 200
        url = upload.json()["data"]["user"]["avatar_url"]
        assert url is not None
        assert ".webp?v=" in url, "the URL must be versioned by its content digest"

        fetched = await db_async_client.get(fetch_path(url))
        assert fetched.status_code == 200
        assert fetched.headers["content-type"] == "image/webp"

        served = Image.open(io.BytesIO(fetched.content))
        assert served.format == "WEBP"
        assert served.size == (512, 512)

    async def test_the_served_image_carries_an_etag_and_a_304_on_revalidation(
        self, db_async_client
    ):
        headers = await signed_up(db_async_client, "etag@example.com")
        upload = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("me.png", png(), "image/png")},
            headers=headers,
        )
        path = fetch_path(upload.json()["data"]["user"]["avatar_url"])

        first = await db_async_client.get(path)
        etag = first.headers["etag"]

        revalidated = await db_async_client.get(path, headers={"if-none-match": etag})

        assert revalidated.status_code == 304
        assert revalidated.content == b""

    async def test_the_url_is_versioned_so_a_replacement_is_not_cached(
        self, db_async_client
    ):
        headers = await signed_up(db_async_client, "version@example.com")

        first = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("a.png", png(colour=(10, 10, 10)), "image/png")},
            headers=headers,
        )
        second = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("b.png", png(colour=(200, 200, 200)), "image/png")},
            headers=headers,
        )

        first_url = first.json()["data"]["user"]["avatar_url"]
        second_url = second.json()["data"]["user"]["avatar_url"]
        assert first_url != second_url, "a replaced image must not share its URL"

    async def test_a_text_file_labelled_png_is_a_415(self, db_async_client):
        headers = await signed_up(db_async_client, "badfile@example.com")

        response = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("fake.png", b"this is plainly not an image", "image/png")},
            headers=headers,
        )

        assert response.status_code == 415
        assert response.json()["error"] == "unsupported_image"

    async def test_an_oversized_upload_is_a_413(self, db_async_client):
        headers = await signed_up(db_async_client, "bigfile@example.com")
        oversized = b"\x89PNG\r\n\x1a\n" + b"0" * 3_000_000

        response = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("big.png", oversized, "image/png")},
            headers=headers,
        )

        assert response.status_code == 413
        assert response.json()["error"] == "image_too_large"

    async def test_a_tiny_image_is_a_413(self, db_async_client):
        headers = await signed_up(db_async_client, "tiny@example.com")

        response = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("tiny.png", png((20, 20)), "image/png")},
            headers=headers,
        )

        assert response.status_code == 413

    async def test_an_unauthenticated_upload_is_a_401(self, db_async_client):
        response = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("me.png", png(), "image/png")},
        )

        assert response.status_code == 401


class TestAvatarDeletion:
    async def test_deleting_is_idempotent(self, db_async_client):
        headers = await signed_up(db_async_client, "delete@example.com")
        await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("me.png", png(), "image/png")},
            headers=headers,
        )

        first = await db_async_client.delete("/api/v1/auth/me/avatar", headers=headers)
        second = await db_async_client.delete("/api/v1/auth/me/avatar", headers=headers)

        assert first.status_code == 204
        assert second.status_code == 204

    async def test_after_deletion_the_url_is_absent_and_the_object_is_gone(
        self, db_async_client
    ):
        headers = await signed_up(db_async_client, "gone@example.com")
        upload = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("me.png", png(), "image/png")},
            headers=headers,
        )
        path = fetch_path(upload.json()["data"]["user"]["avatar_url"])
        assert (await db_async_client.get(path)).status_code == 200

        await db_async_client.delete("/api/v1/auth/me/avatar", headers=headers)

        me = await db_async_client.get("/api/v1/auth/me", headers=headers)
        assert me.json()["data"]["user"]["avatar_url"] is None
        assert (await db_async_client.get(path)).status_code == 404

    async def test_an_avatar_that_never_existed_is_a_404(self, db_async_client):
        response = await db_async_client.get(
            "/api/v1/media/avatar/11111111-1111-4111-8111-111111111111.webp"
        )

        assert response.status_code == 404


class TestIsolation:
    async def test_one_users_deletion_does_not_touch_anothers_object(
        self, db_async_client
    ):
        first = await signed_up(db_async_client, "one@example.com")
        second = await signed_up(db_async_client, "two@example.com")

        uploaded = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("a.png", png(), "image/png")},
            headers=first,
        )
        first_url = uploaded.json()["data"]["user"]["avatar_url"]
        await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("b.png", png(colour=(1, 2, 3)), "image/png")},
            headers=second,
        )

        await db_async_client.delete("/api/v1/auth/me/avatar", headers=second)

        after = await db_async_client.get("/api/v1/auth/me", headers=first)
        assert after.json()["data"]["user"]["avatar_url"] == first_url
        assert (await db_async_client.get(fetch_path(first_url))).status_code == 200

    async def test_each_account_stores_under_its_own_prefix(self, db_async_client):
        headers = await signed_up(db_async_client, "prefix@example.com")
        upload = await db_async_client.post(
            "/api/v1/auth/me/avatar",
            files={"file": ("me.png", png(), "image/png")},
            headers=headers,
        )

        url = upload.json()["data"]["user"]["avatar_url"]
        user_id = upload.json()["data"]["user"]["id"]
        assert f"/{user_id}.webp" in url


class TestShopBackground:
    async def test_uploading_a_background_serves_a_16_by_9_webp(self, db_async_client):
        headers = await signed_up(db_async_client, "shopbg@example.com")

        upload = await db_async_client.post(
            "/api/v1/shops/active/background",
            files={"file": ("bg.jpg", jpeg(), "image/jpeg")},
            headers=headers,
        )

        assert upload.status_code == 200
        url = upload.json()["data"]["background_url"]
        assert url is not None

        fetched = await db_async_client.get(fetch_path(url))
        served = Image.open(io.BytesIO(fetched.content))
        assert served.size == (1600, 900)

    async def test_deleting_a_background_is_idempotent(self, db_async_client):
        headers = await signed_up(db_async_client, "bgdel@example.com")
        await db_async_client.post(
            "/api/v1/shops/active/background",
            files={"file": ("bg.png", png(), "image/png")},
            headers=headers,
        )

        first = await db_async_client.delete(
            "/api/v1/shops/active/background", headers=headers
        )
        second = await db_async_client.delete(
            "/api/v1/shops/active/background", headers=headers
        )

        assert first.status_code == 204
        assert second.status_code == 204

    async def test_a_missing_background_is_a_404(self, db_async_client):
        response = await db_async_client.get(
            "/api/v1/media/shop-background/22222222-2222-4222-8222-222222222222.webp"
        )

        assert response.status_code == 404

    async def test_an_unauthenticated_background_upload_is_a_401(self, db_async_client):
        response = await db_async_client.post(
            "/api/v1/shops/active/background",
            files={"file": ("bg.png", png(), "image/png")},
        )

        assert response.status_code == 401
