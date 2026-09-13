"""Pure identity helpers: normalization, slugify, and token primitives.

No I/O lives here. Nothing in this file opens a session, talks to Redis, or reads a
request, so every function is unit-testable without a database or a network, and
the schema layer can call these directly from a validator.

The one order that matters, applied by every normalizer below:

    raw string -> strip -> fold (NFC / lowercase / digit-fold)
               -> length in characters (matches ``char_length``)
               -> character-class check -> re-check the length

Normalization runs *before* the length check because ``strip()`` shortens a value
and NFC can change its composition. Measuring the raw input rejects values the
database would have accepted and accepts values it would have rejected.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from ecom_be.core.config import Settings
from ecom_be.modules.identity.constants import (
    BIO_MAX,
    EMAIL_MAX,
    EMAIL_MIN,
    FULL_NAME_MAX,
    JOB_TITLE_MAX,
    PASSWORD_MAX,
    PASSWORD_MAX_BYTES,
    PASSWORD_MIN,
    PHONE_MAX_DIGITS,
    PHONE_MAX_INPUT,
    PHONE_MIN_DIGITS,
    SHOP_DESCRIPTION_MAX,
    SHOP_NAME_MAX,
    SHOP_NAME_MIN,
    SLUG_BASE_MAX,
    SLUG_FALLBACK,
    SLUG_MAX,
)

ISSUER = "ecom-be"
_TOKEN_LEEWAY_SECONDS = 5

# Deliberately structural rather than RFC 5322: a full grammar regex is famously
# unmaintainable and still cannot tell whether an address receives mail. The
# Pydantic ``EmailStr`` on the request schema does the exhaustive grammar check;
# this is the shared rule the pure helpers can apply on their own.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
_PHONE_PATTERN = re.compile(r"^\+?[0-9]{7,15}$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")
# Every control character except a newline, which multiline fields allow.
_CONTROL_NO_NEWLINE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MULTI_NEWLINE = re.compile(r"\n{3,}")

_MULTILINE_LIMITS = {"bio": BIO_MAX, "shop_description": SHOP_DESCRIPTION_MAX}
_SINGLE_LINE_LIMITS = {
    "full_name": (1, FULL_NAME_MAX),
    "job_title": (0, JOB_TITLE_MAX),
    "shop_name": (SHOP_NAME_MIN, SHOP_NAME_MAX),
}


class InvalidAccessToken(Exception):
    """A bearer token that failed its signature, expiry, issuer, or type check."""


def new_id() -> str:
    """A fresh uuid4 as a string, the shape the id claims use."""

    return str(uuid.uuid4())


def _fold(value: str, field: str) -> str:
    """Normalize form, strip surrounding whitespace, and reject control characters."""

    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if _CONTROL_NO_NEWLINE.search(normalized):
        raise ValueError(f"{field} contains control characters")
    return normalized


def normalize_email(value: str) -> str:
    """Strip, lowercase, and check an email address.

    Lowercasing here is what lets the database hold an ``email = lower(email)``
    check and a ``citext`` column without either being a surprise.
    """

    if not isinstance(value, str):
        raise ValueError("email must be a string")
    normalized = value.strip().lower()
    if not EMAIL_MIN <= len(normalized) <= EMAIL_MAX:
        raise ValueError("email length is out of range")
    if not _EMAIL_PATTERN.match(normalized):
        raise ValueError("email is not a valid address")
    return normalized


def normalize_name(value: str, *, field: str) -> str:
    """Fold a single-line text field: NFC, stripped, no newlines, bounded.

    A newline is rejected in a name on purpose. It is not pedantry about input: a
    name containing newlines is a layout injection waiting for the first component
    that renders it.
    """

    normalized = _fold(value, field)
    if "\n" in normalized or "\r" in normalized:
        raise ValueError(f"{field} must be a single line")
    minimum, maximum = _SINGLE_LINE_LIMITS[field]
    if not minimum <= len(normalized) <= maximum:
        raise ValueError(f"{field} length is out of range")
    return normalized


def normalize_multiline(value: str, *, field: str) -> str:
    """Fold a multi-line text field: NFC, stripped, blank runs collapsed.

    Newlines are allowed here because a person writes paragraphs about themselves.
    Three or more consecutive newlines collapse to one blank line, which is a
    formatting decision the normalizer makes once rather than every renderer
    making differently.
    """

    normalized = _fold(value, field)
    normalized = _MULTI_NEWLINE.sub("\n\n", normalized).strip()
    if len(normalized) > _MULTILINE_LIMITS[field]:
        raise ValueError(f"{field} length is out of range")
    return normalized


def normalize_phone(value: str, *, field: str) -> str | None:
    """Fold a phone number to ``+?digits``, or ``None`` when it is blank.

    Blank means absent rather than invalid, because the field is optional and an
    empty form input arrives as an empty string, not as a missing key.
    """

    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if len(stripped) > PHONE_MAX_INPUT:
        raise ValueError(f"{field} is too long")
    candidate = re.sub(r"[\s\-().]", "", stripped)
    if not _PHONE_PATTERN.match(candidate):
        raise ValueError(f"{field} is not a valid phone number")
    digits = candidate.lstrip("+")
    if not PHONE_MIN_DIGITS <= len(digits) <= PHONE_MAX_DIGITS:
        raise ValueError(f"{field} digit count is out of range")
    return ("+" if candidate.startswith("+") else "") + digits


def slugify(value: str) -> str:
    """Derive a URL-safe slug from a shop name.

    NFKD decomposition then an ascii fold is what turns ``Cửa hàng`` into
    ``cua-hang``: the combining marks are dropped rather than transliterated, so
    the result is stable regardless of the input's normalization form.
    """

    if not isinstance(value, str):
        raise ValueError("slug source must be a string")
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_SLUG.sub("-", ascii_only).strip("-")
    if not slug:
        return SLUG_FALLBACK
    return slug[:SLUG_BASE_MAX].strip("-") or SLUG_FALLBACK


def slug_with_suffix(base: str, suffix: int) -> str:
    """Append a numeric collision suffix, staying inside the column bound."""

    text = str(suffix)
    trimmed = base[: SLUG_MAX - len(text) - 1].strip("-")
    return f"{trimmed or SLUG_FALLBACK}-{text}"


def validate_password(value: str) -> None:
    """Check the character cap and the byte cap, because Argon2 takes bytes.

    Both are needed. ``PASSWORD_MAX`` bounds the request body; the byte cap stops a
    multi-byte password from exceeding the hashing library's own limit and
    surfacing as a 500 instead of a 422.
    """

    if not isinstance(value, str):
        raise ValueError("password must be a string")
    if len(value) < PASSWORD_MIN:
        raise ValueError("password is too short")
    if len(value) > PASSWORD_MAX:
        raise ValueError("password is too long")
    if len(value.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError("password is too long")
    if not value.strip():
        raise ValueError("password cannot be whitespace only")


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 hex digest that is the only form ever stored."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    """Return a fresh opaque refresh token and its digest."""

    token = secrets.token_urlsafe(32)
    return token, hash_refresh_token(token)


def issue_access_token(
    settings: Settings,
    *,
    user_id: str,
    active_shop_id: str,
    now: datetime | None = None,
    issuer: str = ISSUER,
    token_type: Literal["access", "refresh"] = "access",
) -> str:
    """Mint a short-lived access token.

    The token carries no roles and no permissions. Authority is resolved from the
    database per request, so a revoked membership or a role change takes effect on
    the next request rather than when the token expires.

    ``issuer`` and ``token_type`` are parameterised so the rejection paths can be
    tested directly instead of by forging a token by hand.
    """

    issued = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(active_shop_id),
        "type": token_type,
        "iss": issuer,
        "jti": uuid.uuid4().hex,
        "iat": issued,
        "exp": issued + timedelta(seconds=settings.access_token_ttl_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    """Verify a bearer token and return its claims.

    Four things are asserted, and each one closes a real hole:

    * the signature, so a token was minted by this service;
    * ``exp`` with a small leeway, so an expired token is not honoured;
    * ``iss``, so a token minted by another service is refused;
    * ``type == "access"``, so a refresh value can never be presented as a bearer.
    """

    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            leeway=_TOKEN_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "sub", "sid", "type", "iss", "jti"]},
        )
    except jwt.PyJWTError as error:
        raise InvalidAccessToken(str(error)) from error

    if claims.get("type") != "access":
        raise InvalidAccessToken("wrong token type")
    if not isinstance(claims.get("sub"), str) or not isinstance(claims.get("sid"), str):
        raise InvalidAccessToken("missing subject claims")
    return claims
