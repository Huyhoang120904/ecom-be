"""Contract: the image pipeline.

Real bytes go in and real bytes come out, so these tests need no filesystem, no
bucket, and no request. Every branch the pipeline can take is reachable from here.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.errors.media import ImageTooLarge, UnsupportedImage
from app.utils import media as utils

MAX_BYTES = 2_097_152


def png(
    size: tuple[int, int] = (800, 600), colour: tuple[int, int, int] = (10, 20, 30)
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg(size: tuple[int, int] = (800, 600)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buffer, format="JPEG")
    return buffer.getvalue()


def webp(size: tuple[int, int] = (800, 600)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (50, 100, 200)).save(buffer, format="WEBP")
    return buffer.getvalue()


def decoded(payload: bytes) -> Image.Image:
    return Image.open(io.BytesIO(payload))


class TestFormatSniffing:
    @pytest.mark.parametrize(
        ("factory", "declared"),
        [
            (png, "image/png"),
            (jpeg, "image/jpeg"),
            (webp, "image/webp"),
        ],
    )
    def test_an_accepted_format_matching_its_declared_type_passes(
        self, factory, declared
    ):
        logical, _key = utils.normalize_avatar(
            factory(), declared_content_type=declared, max_bytes=MAX_BYTES
        )

        assert decoded(logical).format == "WEBP"

    @pytest.mark.parametrize(
        ("factory", "wrong"),
        [
            (png, "image/jpeg"),
            (jpeg, "image/png"),
            (webp, "image/jpeg"),
        ],
    )
    def test_a_renamed_file_is_rejected_by_its_magic_bytes(self, factory, wrong):
        """A PNG labelled as a JPEG is refused, because the label is not evidence."""

        with pytest.raises(UnsupportedImage):
            utils.normalize_avatar(
                factory(), declared_content_type=wrong, max_bytes=MAX_BYTES
            )

    def test_a_non_image_is_rejected(self):
        with pytest.raises(UnsupportedImage):
            utils.normalize_avatar(
                b"this is plainly not an image",
                declared_content_type="image/png",
                max_bytes=MAX_BYTES,
            )

    def test_an_empty_payload_is_rejected(self):
        with pytest.raises(UnsupportedImage):
            utils.normalize_avatar(
                b"", declared_content_type="image/png", max_bytes=MAX_BYTES
            )

    def test_a_truncated_image_is_rejected(self):
        truncated = png()[:100]

        with pytest.raises(UnsupportedImage):
            utils.normalize_avatar(
                truncated, declared_content_type="image/png", max_bytes=MAX_BYTES
            )


class TestSizeBounds:
    def test_an_oversized_upload_is_refused_before_decoding(self):
        """The cap runs first, so a huge payload is never handed to Image.open."""

        huge = b"\x89PNG\r\n\x1a\n" + b"0" * 3_000_000

        with pytest.raises(ImageTooLarge):
            utils.normalize_avatar(
                huge, declared_content_type="image/png", max_bytes=MAX_BYTES
            )

    def test_a_payload_exactly_at_the_cap_is_not_refused_for_size(self):
        """One byte over is refused; at the cap the decision moves to the decoder."""

        exactly = png()
        assert len(exactly) <= MAX_BYTES

        logical, _key = utils.normalize_avatar(
            exactly, declared_content_type="image/png", max_bytes=len(exactly)
        )

        assert logical

    def test_a_payload_one_byte_over_the_cap_is_refused(self):
        payload = png()

        with pytest.raises(ImageTooLarge):
            utils.normalize_avatar(
                payload, declared_content_type="image/png", max_bytes=len(payload) - 1
            )

    def test_an_image_below_the_minimum_side_is_rejected(self):
        with pytest.raises(ImageTooLarge):
            utils.normalize_avatar(
                png((20, 20)), declared_content_type="image/png", max_bytes=MAX_BYTES
            )

    def test_a_short_side_below_the_minimum_is_rejected(self):
        """The bound is on the short side, not on the area."""

        with pytest.raises(ImageTooLarge):
            utils.normalize_avatar(
                png((5000, 20)), declared_content_type="image/png", max_bytes=MAX_BYTES
            )

    def test_an_image_above_the_maximum_side_is_rejected(self):
        with pytest.raises(ImageTooLarge):
            utils.normalize_avatar(
                png((4097, 100)), declared_content_type="image/png", max_bytes=MAX_BYTES
            )

    def test_an_image_at_both_bounds_is_accepted(self):
        logical, _key = utils.normalize_avatar(
            png((32, 4096)), declared_content_type="image/png", max_bytes=MAX_BYTES
        )

        assert decoded(logical).size == utils.AVATAR_SIZE


class TestNormalization:
    def test_an_avatar_becomes_a_512_square_webp(self):
        logical, _key = utils.normalize_avatar(
            png((3000, 1000)), declared_content_type="image/png", max_bytes=MAX_BYTES
        )

        image = decoded(logical)
        assert image.format == "WEBP"
        assert image.size == (512, 512)

    def test_a_background_becomes_a_1600_by_900_webp(self):
        logical, _key = utils.normalize_background(
            png((1000, 4000)), declared_content_type="image/png", max_bytes=MAX_BYTES
        )

        assert decoded(logical).size == (1600, 900)

    def test_a_tall_image_is_centre_cropped_rather_than_letterboxed(self):
        """A wide photo must lose its edges, not gain bars."""

        logical, _key = utils.normalize_avatar(
            png((2000, 500), (250, 0, 0)),
            declared_content_type="image/png",
            max_bytes=MAX_BYTES,
        )

        image = decoded(logical).convert("RGB")
        assert image.size == (512, 512)
        # A single solid colour means no bars were introduced. WebP is lossy, so this
        # compares within a tolerance rather than for exact equality: the point is
        # "red everywhere", not "this exact byte".
        for corner in ((0, 0), (511, 0), (0, 511), (511, 511), (256, 256)):
            red, green, blue = image.getpixel(corner)
            assert red > 200, f"{corner} is not red: {(red, green, blue)}"
            assert green < 40 and blue < 40, (
                f"{corner} is not red: {(red, green, blue)}"
            )

    def test_a_square_image_needs_no_crop(self):
        logical, _key = utils.normalize_avatar(
            png((600, 600)), declared_content_type="image/png", max_bytes=MAX_BYTES
        )

        assert decoded(logical).size == (512, 512)


class TestMetadataStripping:
    def test_exif_is_dropped(self):
        """A phone photo carries GPS coordinates; a public avatar must not.

        The EXIF block is written as real GPS degrees rather than a dict, because an
        invalid tag would fail while *writing the fixture* and prove nothing about
        whether the pipeline strips metadata.
        """

        from PIL.TiffImagePlugin import IFDRational

        buffer = io.BytesIO()
        image = Image.new("RGB", (600, 600), (1, 2, 3))
        exif = image.getexif()
        # Real GPS degrees, written with IFDRational because that is the type the
        # format expects for a rational tag.
        exif[0x8825] = {
            1: "N",
            2: (IFDRational(37, 1), IFDRational(46, 1), IFDRational(30, 1)),
            3: "E",
            4: (IFDRational(122, 1), IFDRational(25, 1), IFDRational(0, 1)),
        }
        image.save(buffer, format="JPEG", exif=exif)

        source = buffer.getvalue()
        assert Image.open(io.BytesIO(source)).getexif(), (
            "the fixture must actually carry metadata, or this proves nothing"
        )

        logical, _key = utils.normalize_avatar(
            source, declared_content_type="image/jpeg", max_bytes=MAX_BYTES
        )

        assert not decoded(logical).getexif(), "the metadata block survived"

    def test_a_source_without_exif_still_normalizes(self):
        logical, _key = utils.normalize_avatar(
            png(), declared_content_type="image/png", max_bytes=MAX_BYTES
        )

        assert decoded(logical).format == "WEBP"


class TestDigest:
    def test_the_same_input_bytes_produce_the_same_digest(self):
        """Which is what makes a re-upload a no-op instead of a second object."""

        payload = png()

        _first, first_key = utils.normalize_avatar(
            payload, declared_content_type="image/png", max_bytes=MAX_BYTES
        )
        _second, second_key = utils.normalize_avatar(
            payload, declared_content_type="image/png", max_bytes=MAX_BYTES
        )

        assert first_key == second_key

    def test_different_input_bytes_produce_different_digests(self):
        _first, first_key = utils.normalize_avatar(
            png((600, 600), (1, 1, 1)),
            declared_content_type="image/png",
            max_bytes=MAX_BYTES,
        )
        _second, second_key = utils.normalize_avatar(
            png((600, 600), (2, 2, 2)),
            declared_content_type="image/png",
            max_bytes=MAX_BYTES,
        )

        assert first_key != second_key

    def test_the_digest_is_over_the_stored_bytes(self):
        logical, key = utils.normalize_avatar(
            png(), declared_content_type="image/png", max_bytes=MAX_BYTES
        )

        assert key == utils.content_digest(logical)
        assert len(key) == 64
