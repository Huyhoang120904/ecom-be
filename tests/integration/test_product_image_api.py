"""Contract: product and variant images.

Marked ``db`` because tenancy, the composite key and the per-scope ordering are queries
and constraints. Storage is a temporary directory (see ``db_async_client``).
"""

from __future__ import annotations

import io

import pytest
from catalog_helpers import (
    PRODUCTS,
    create_product,
    make_png,
    make_variant,
    new_id,
    polo,
    upload_image,
)
from PIL import Image
from sqlalchemy import text

from app.constants.catalog import PRODUCT_IMAGES_MAX, VARIANT_IMAGES_MAX

pytestmark = [pytest.mark.anyio, pytest.mark.db]


def path_of(url: str) -> str:
    return "/" + url.split("://", 1)[1].split("/", 1)[1]


async def variants_of(client, owner, product_id):
    listed = await client.get(
        f"{PRODUCTS}/{product_id}/variants", headers=owner.headers
    )
    return listed.json()["data"]


async def positions(client, owner, product_id, variant_id=None):
    product = (
        await client.get(f"{PRODUCTS}/{product_id}", headers=owner.headers)
    ).json()["data"]
    if variant_id is None:
        images = product["images"]
    else:
        variant = next(v for v in product["variants"] if v["id"] == variant_id)
        images = variant["images"]
    return [(image["id"], image["position"]) for image in images]


class TestUpload:
    async def test_a_product_image_is_stored_and_served_as_webp(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await upload_image(db_async_client, owner.headers, product["id"])

        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["variant_id"] is None
        assert data["position"] == 0
        served = await db_async_client.get(path_of(data["url"]))
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/webp"
        assert Image.open(io.BytesIO(served.content)).format == "WEBP"

    async def test_a_large_photo_is_shrunk_to_fit_without_cropping(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await upload_image(
            db_async_client,
            owner.headers,
            product["id"],
            data=make_png(3200, 1000),
        )

        served = await db_async_client.get(path_of(response.json()["data"]["url"]))
        size = Image.open(io.BytesIO(served.content)).size
        assert size[0] == 1600
        assert size[1] == 500  # the aspect ratio is kept, nothing is cropped

    async def test_a_small_photo_is_not_enlarged(self, db_async_client, owner, seeded):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await upload_image(
            db_async_client, owner.headers, product["id"], data=make_png(100, 60)
        )

        served = await db_async_client.get(path_of(response.json()["data"]["url"]))
        assert Image.open(io.BytesIO(served.content)).size == (100, 60)

    async def test_the_content_type_must_match_the_bytes(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await upload_image(
            db_async_client, owner.headers, product["id"], content_type="image/jpeg"
        )

        assert response.status_code == 415
        assert response.json()["error"] == "unsupported_image"

    async def test_non_images_are_rejected(self, db_async_client, owner, seeded):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await upload_image(
            db_async_client, owner.headers, product["id"], data=b"not an image"
        )

        assert response.status_code == 415

    async def test_a_variant_can_have_several_images_of_its_own(
        self, db_async_client, owner, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)
        black = (await variants_of(db_async_client, owner, product["id"]))[0]

        first = await upload_image(
            db_async_client, owner.headers, product["id"], variant_id=black["id"]
        )
        second = await upload_image(
            db_async_client, owner.headers, product["id"], variant_id=black["id"]
        )
        shared = await upload_image(db_async_client, owner.headers, product["id"])

        assert [
            first.json()["data"]["position"],
            second.json()["data"]["position"],
        ] == [
            0,
            1,
        ]
        # Positions are per scope: the product's own images count from zero too.
        assert shared.json()["data"]["position"] == 0
        detail = (
            await db_async_client.get(
                f"{PRODUCTS}/{product['id']}", headers=owner.headers
            )
        ).json()["data"]
        assert len(detail["images"]) == 1
        variant = next(v for v in detail["variants"] if v["id"] == black["id"])
        assert len(variant["images"]) == 2

    async def test_a_variant_of_another_product_is_refused(
        self, db_async_client, owner, seeded
    ):
        one = await polo(db_async_client, owner.headers, seeded)
        two = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"], "Other"
        )
        foreign = (await variants_of(db_async_client, owner, one["id"]))[0]

        response = await upload_image(
            db_async_client, owner.headers, two["id"], variant_id=foreign["id"]
        )

        assert response.status_code == 422
        assert response.json()["error"] == "image_variant_invalid"

    async def test_an_unknown_variant_is_refused(self, db_async_client, owner, seeded):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )

        response = await upload_image(
            db_async_client, owner.headers, product["id"], variant_id=new_id()
        )

        assert response.status_code == 422

    async def test_the_per_scope_limits_are_enforced(
        self, db_async_client, owner, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)
        variant = (await variants_of(db_async_client, owner, product["id"]))[0]

        for _ in range(PRODUCT_IMAGES_MAX):
            assert (
                await upload_image(db_async_client, owner.headers, product["id"])
            ).status_code == 201
        over_product = await upload_image(db_async_client, owner.headers, product["id"])
        for _ in range(VARIANT_IMAGES_MAX):
            assert (
                await upload_image(
                    db_async_client,
                    owner.headers,
                    product["id"],
                    variant_id=variant["id"],
                )
            ).status_code == 201
        over_variant = await upload_image(
            db_async_client, owner.headers, product["id"], variant_id=variant["id"]
        )

        assert over_product.status_code == 409
        assert over_product.json()["error"] == "image_limit_reached"
        assert over_variant.status_code == 409


class TestOrdering:
    async def three(self, client, owner, seeded):
        product = await create_product(
            client, owner.headers, seeded.categories["ao-thun"]
        )
        ids = []
        for _ in range(3):
            response = await upload_image(client, owner.headers, product["id"])
            ids.append(response.json()["data"]["id"])
        return product, ids

    async def test_moving_an_image_keeps_a_dense_order(
        self, db_async_client, owner, seeded
    ):
        product, (a, b, c) = await self.three(db_async_client, owner, seeded)

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}/images/{c}",
            json={"position": 0},
            headers=owner.headers,
        )

        assert response.status_code == 200
        assert [(i["id"], i["position"]) for i in response.json()["data"]] == [
            (c, 0),
            (a, 1),
            (b, 2),
        ]
        assert await positions(db_async_client, owner, product["id"]) == [
            (c, 0),
            (a, 1),
            (b, 2),
        ]

    async def test_a_position_outside_the_range_is_refused(
        self, db_async_client, owner, seeded
    ):
        product, (a, _b, _c) = await self.three(db_async_client, owner, seeded)

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}/images/{a}",
            json={"position": 3},
            headers=owner.headers,
        )

        assert response.status_code == 422
        assert response.json()["error"] == "invalid_image_position"

    async def test_the_body_takes_only_a_position(self, db_async_client, owner, seeded):
        product, (a, _b, _c) = await self.three(db_async_client, owner, seeded)

        response = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}/images/{a}",
            json={"position": 1, "variant_id": new_id()},
            headers=owner.headers,
        )

        assert response.status_code == 422

    async def test_deleting_the_middle_image_closes_the_gap(
        self, db_async_client, owner, seeded
    ):
        product, (a, b, c) = await self.three(db_async_client, owner, seeded)

        response = await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}/images/{b}", headers=owner.headers
        )

        assert response.status_code == 204
        assert await positions(db_async_client, owner, product["id"]) == [
            (a, 0),
            (c, 1),
        ]


class TestCleanup:
    async def test_deleting_a_variant_removes_only_its_images(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await polo(db_async_client, owner.headers, seeded)
        first, second = (await variants_of(db_async_client, owner, product["id"]))[:2]
        gone = await upload_image(
            db_async_client, owner.headers, product["id"], variant_id=first["id"]
        )
        kept = await upload_image(
            db_async_client, owner.headers, product["id"], variant_id=second["id"]
        )
        gone_url = path_of(gone.json()["data"]["url"])
        kept_url = path_of(kept.json()["data"]["url"])

        await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}/variants/{first['id']}", headers=owner.headers
        )

        assert (await db_async_client.get(gone_url)).status_code == 404
        assert (await db_async_client.get(kept_url)).status_code == 200
        rows = await db_session.scalar(
            text("SELECT count(*) FROM product_images WHERE product_id = :id"),
            {"id": product["id"]},
        )
        assert rows == 1

    async def test_deleting_a_product_removes_all_its_images(
        self, db_async_client, db_session, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        response = await upload_image(db_async_client, owner.headers, product["id"])
        url = path_of(response.json()["data"]["url"])

        await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}", headers=owner.headers
        )

        assert (await db_async_client.get(url)).status_code == 404
        rows = await db_session.scalar(
            text("SELECT count(*) FROM product_images WHERE product_id = :id"),
            {"id": product["id"]},
        )
        assert rows == 0

    async def test_identical_uploads_own_separate_objects(
        self, db_async_client, owner, seeded
    ):
        """Deleting one image must never remove another's file."""

        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        same = make_png(80, 80, "blue")
        one = await upload_image(
            db_async_client, owner.headers, product["id"], data=same
        )
        two = await upload_image(
            db_async_client, owner.headers, product["id"], data=same
        )

        await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}/images/{one.json()['data']['id']}",
            headers=owner.headers,
        )

        survivor = await db_async_client.get(path_of(two.json()["data"]["url"]))
        assert survivor.status_code == 200


class TestPermissionsAndTenancy:
    async def test_a_viewer_cannot_upload(self, db_async_client, owner, demote, seeded):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        await demote(owner, "viewer")

        response = await upload_image(db_async_client, owner.headers, product["id"])

        assert response.status_code == 403

    async def test_another_shops_product_is_a_404(
        self, db_async_client, register_seller, seeded
    ):
        alice = await register_seller("alice@example.com", "Alice Shop")
        bob = await register_seller("bob@example.com", "Bob Shop")
        product = await create_product(
            db_async_client, alice.headers, seeded.categories["ao-thun"]
        )
        image = (
            await upload_image(db_async_client, alice.headers, product["id"])
        ).json()["data"]

        upload = await upload_image(db_async_client, bob.headers, product["id"])
        move = await db_async_client.patch(
            f"{PRODUCTS}/{product['id']}/images/{image['id']}",
            json={"position": 0},
            headers=bob.headers,
        )
        delete = await db_async_client.delete(
            f"{PRODUCTS}/{product['id']}/images/{image['id']}", headers=bob.headers
        )

        assert {upload.status_code, move.status_code, delete.status_code} == {404}

    async def test_an_image_of_another_product_is_not_found_by_id(
        self, db_async_client, owner, seeded
    ):
        one = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"], "One"
        )
        two = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"], "Two"
        )
        image = (await upload_image(db_async_client, owner.headers, one["id"])).json()[
            "data"
        ]

        response = await db_async_client.delete(
            f"{PRODUCTS}/{two['id']}/images/{image['id']}", headers=owner.headers
        )

        assert response.status_code == 404
        assert response.json()["error"] == "product_image_not_found"

    async def test_an_unknown_image_id_serves_a_404(self, db_async_client):
        response = await db_async_client.get(
            f"/api/v1/media/product-image/{new_id()}.webp"
        )

        assert response.status_code == 404

    async def test_variant_creation_still_works_alongside_images(
        self, db_async_client, owner, seeded
    ):
        product = await create_product(
            db_async_client, owner.headers, seeded.categories["ao-thun"]
        )
        await upload_image(db_async_client, owner.headers, product["id"])

        variant = await make_variant(
            db_async_client,
            owner.headers,
            product["id"],
            "A",
            1,
            [seeded.option("color", "Black"), seeded.option("size", "S")],
        )

        assert variant["images"] == []
