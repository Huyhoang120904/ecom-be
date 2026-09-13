"""Pure image pipeline: sniff, bound, normalize, digest.

Taking bytes and returning bytes is what makes every branch here testable with no
filesystem, no bucket, and no request. The media service is then a thin layer that
moves those bytes to storage.

The ordering of the checks is load-bearing: the size cap is enforced *before* any
decode, because ``Image.open`` on a hostile 200 MB payload is the denial of service
that reading the whole file first would already have caused.
"""

from __future__ import annotations

import hashlib
import io
from typing import Final

from PIL import Image, UnidentifiedImageError

from app.errors.media import ImageTooLarge, UnsupportedImage

# Pillow's own format names, mapped to the media types accepted in a request. The
# declared type is compared against this, so a renamed file cannot slip through.
ACCEPTED_FORMATS: Final[dict[str, str]] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

MIN_SIDE: Final = 32
MAX_SIDE: Final = 4096

AVATAR_SIZE: Final[tuple[int, int]] = (512, 512)
BACKGROUND_SIZE: Final[tuple[int, int]] = (1600, 900)

WEBP_QUALITY: Final = 82
# Slower to encode, smaller to serve, and deterministic: the same input bytes always
# produce the same output bytes, which is what makes the content digest stable.
WEBP_METHOD: Final = 4


def _center_crop_to(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Crop to the target aspect ratio from the centre, then resize.

    Cropping before resizing is what avoids the letterboxing that a plain resize
    would introduce: an avatar is a square, and a wide photo should lose its edges
    rather than gain bars.
    """

    target_ratio = size[0] / size[1]
    width, height = image.size
    current_ratio = width / height

    if current_ratio > target_ratio:
        new_width = int(height * target_ratio)
        left = (width - new_width) // 2
        box = (left, 0, left + new_width, height)
    else:
        new_height = int(width / target_ratio)
        top = (height - new_height) // 2
        box = (0, top, width, top + new_height)

    return image.crop(box).resize(size, Image.Resampling.LANCZOS)


def content_digest(payload: bytes) -> str:
    """A stable key fragment for a normalised payload."""

    return hashlib.sha256(payload).hexdigest()


def normalize(
    image_bytes: bytes,
    *,
    declared_content_type: str,
    size: tuple[int, int],
    max_bytes: int,
) -> tuple[bytes, str]:
    """Validate and normalize an upload.

    Returns the stored bytes and their content digest. The digest is computed over
    the *normalized* payload, so re-uploading the same photo produces the same key
    and therefore the same object rather than a duplicate.
    """

    if len(image_bytes) > max_bytes:
        raise ImageTooLarge

    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            # A cheap integrity pass first: verify() catches a truncated file without
            # fully decoding it.
            probe.verify()
        reopened = Image.open(io.BytesIO(image_bytes))
    except (UnidentifiedImageError, OSError) as error:
        raise UnsupportedImage from error

    real_type = ACCEPTED_FORMATS.get(reopened.format or "")
    if real_type is None or real_type != declared_content_type:
        # The declared type is compared against the sniffed one rather than trusted:
        # a browser will happily post any bytes with any label.
        raise UnsupportedImage

    width, height = reopened.size
    if min(width, height) < MIN_SIDE:
        raise ImageTooLarge
    if max(width, height) > MAX_SIDE:
        raise ImageTooLarge

    converted = reopened.convert("RGB")
    normalized = _center_crop_to(converted, size)

    buffer = io.BytesIO()
    # No ``exif=`` and no ``icc_profile=``: the metadata block is dropped. That is
    # not cosmetic. A phone photo carries GPS coordinates, and serving a seller's
    # home location from a public avatar endpoint is a privacy leak.
    normalized.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    payload = buffer.getvalue()

    return payload, content_digest(payload)


def normalize_avatar(
    image_bytes: bytes, *, declared_content_type: str, max_bytes: int
) -> tuple[bytes, str]:
    return normalize(
        image_bytes,
        declared_content_type=declared_content_type,
        size=AVATAR_SIZE,
        max_bytes=max_bytes,
    )


def normalize_background(
    image_bytes: bytes, *, declared_content_type: str, max_bytes: int
) -> tuple[bytes, str]:
    return normalize(
        image_bytes,
        declared_content_type=declared_content_type,
        size=BACKGROUND_SIZE,
        max_bytes=max_bytes,
    )
