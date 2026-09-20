"""Contract: the product-photo pipeline.

Pure: bytes in, bytes out. Unlike an avatar, a product photo is never cropped and never
enlarged, because its aspect ratio is part of the picture.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.errors.media import ImageTooLarge, UnsupportedImage
from app.utils.media import normalize_product_image

MAX_BYTES = 10_000_000


def png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "green").save(buffer, format="PNG")
    return buffer.getvalue()


def run(data: bytes, content_type: str = "image/png") -> tuple[bytes, str]:
    return normalize_product_image(
        data, declared_content_type=content_type, max_bytes=MAX_BYTES
    )


def size_of(payload: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(payload)).size


def test_the_output_is_webp():
    payload, _ = run(png(200, 100))

    assert Image.open(io.BytesIO(payload)).format == "WEBP"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ((3200, 1000), (1600, 500)),  # wide: limited by width
        ((1000, 3200), (500, 1600)),  # tall: limited by height
        ((2000, 2000), (1600, 1600)),
    ],
)
def test_a_large_photo_is_shrunk_to_fit_keeping_its_ratio(source, expected):
    payload, _ = run(png(*source))

    assert size_of(payload) == expected


@pytest.mark.parametrize("source", [(100, 60), (1600, 1600), (1600, 40)])
def test_a_photo_inside_the_box_keeps_its_size(source):
    payload, _ = run(png(*source))

    assert size_of(payload) == source


def test_the_digest_is_stable_for_identical_input():
    assert run(png(200, 100))[1] == run(png(200, 100))[1]
    assert run(png(200, 100))[1] != run(png(201, 100))[1]


def test_the_declared_type_must_match_the_bytes():
    with pytest.raises(UnsupportedImage):
        run(png(200, 100), "image/jpeg")


def test_garbage_is_not_an_image():
    with pytest.raises(UnsupportedImage):
        run(b"definitely not an image")


def test_an_oversized_payload_is_refused_before_it_is_decoded():
    with pytest.raises(ImageTooLarge):
        normalize_product_image(
            png(200, 100), declared_content_type="image/png", max_bytes=10
        )


def test_a_tiny_image_is_refused():
    with pytest.raises(ImageTooLarge):
        run(png(8, 8))
