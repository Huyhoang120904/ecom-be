"""Identity domain errors.

Each class carries its own status code and stable ``code``, so a service raises
meaning and ``core.errors`` renders the transport. That is why there is no mapping
table from exception type to status anywhere: the class *is* the mapping.

``message`` is a fixed, safe string per class. A message assembled from request data
would reintroduce reflection, and ``AGENTS.md`` forbids returning exception detail
to a client.
"""

from __future__ import annotations

from app.core.errors import AppError


class InvalidCredentials(AppError):
    code = "invalid_credentials"
    status_code = 401
    message = "Email or password is incorrect"


class InvalidToken(AppError):
    code = "invalid_token"
    status_code = 401
    message = "Authentication required"


class AccountInactive(AppError):
    code = "account_inactive"
    status_code = 401
    message = "This account is not active"


class ShopNotAccessible(AppError):
    code = "shop_not_accessible"
    status_code = 401
    message = "The active shop is not available"


class NotAMember(AppError):
    code = "not_a_member"
    status_code = 403
    message = "You do not have access to this shop"


class Forbidden(AppError):
    code = "forbidden"
    status_code = 403
    message = "You do not have permission to do that"


class AccountDeactivated(AppError):
    code = "account_deactivated"
    status_code = 403
    message = "This account is deactivated"


class EmailTaken(AppError):
    code = "email_taken"
    status_code = 409
    message = "That email address is already registered"


class RateLimited(AppError):
    code = "rate_limited"
    status_code = 429
    message = "Too many attempts. Try again shortly"


class ConfirmationMismatch(AppError):
    code = "confirmation_mismatch"
    status_code = 422
    message = "The confirmation value did not match"


class UnsupportedImage(AppError):
    code = "unsupported_image"
    status_code = 415
    message = "Upload a JPEG, PNG, or WebP image"


class ImageTooLarge(AppError):
    code = "image_too_large"
    status_code = 413
    message = "That image is too large"
