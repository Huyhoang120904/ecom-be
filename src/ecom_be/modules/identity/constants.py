"""Every bound in the identity contract, in one place.

These numbers are the contract. A schema that hardcodes its own literal drifts
from the database ``CHECK``, and the drift surfaces as a 500 at insert time instead
of a 422 at the boundary. The migration, the Pydantic schemas, and the test suite
all read these.
"""

from __future__ import annotations

EMAIL_MIN = 3
EMAIL_MAX = 254

PASSWORD_MIN = 12
PASSWORD_MAX = 128
# Argon2's input is bytes, and a multi-byte password can exceed the library's own
# limit while staying inside the character cap.
PASSWORD_MAX_BYTES = 256

FULL_NAME_MIN = 1
FULL_NAME_MAX = 120

BIO_MAX = 500

# The raw input bound. ``normalize_phone`` then enforces the digit count after
# folding, which is the bound that matters.
PHONE_MAX_INPUT = 32
PHONE_MIN_DIGITS = 7
PHONE_MAX_DIGITS = 15

JOB_TITLE_MAX = 80

SHOP_NAME_MIN = 2
SHOP_NAME_MAX = 80
SHOP_DESCRIPTION_MAX = 300
SHOP_WEBSITE_MAX = 255

MEDIA_KEY_MAX = 128
ACCESS_TOKEN_MAX = 4096
URL_MAX = 500

SLUG_MAX = 80
# Room for a "-" and a collision suffix, so appending never overflows the column.
SLUG_BASE_MAX = 72
SLUG_FALLBACK = "shop"

# Multipart part name for both image uploads.
UPLOAD_FIELD_NAME = "file"

ROLE_KEY_MAX = 64
ROLE_NAME_MAX = 80
PERMISSION_KEY_MAX = 64
PERMISSION_DESCRIPTION_MAX = 200
