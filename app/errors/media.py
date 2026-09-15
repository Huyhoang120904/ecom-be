"""Media module errors.

They live here rather than in ``identity/errors.py`` because the failure is about an
image, not about an account: the identity module stores the resulting key and never
learns why the bytes were refused.
"""

from __future__ import annotations

from app.core.errors import AppError


class UnsupportedImage(AppError):
    code = "unsupported_image"
    status_code = 415
    message = "Upload a JPEG, PNG, or WebP image"


class ImageTooLarge(AppError):
    code = "image_too_large"
    status_code = 413
    message = "That image is too large"


class ImageNotFound(AppError):
    code = "not_found"
    status_code = 404
    message = "Resource not found"
