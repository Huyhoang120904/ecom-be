"""Bounds on an account: its credentials and its profile fields.

These numbers are the contract. A schema that hardcodes its own literal drifts from
the database ``CHECK``, and the drift surfaces as a 500 at insert time instead of a
422 at the boundary. The migration, the Pydantic schemas, and the test suite all
read these.
"""

EMAIL_MIN = 3

EMAIL_MAX = 254

PASSWORD_MIN = 12

PASSWORD_MAX = 128

# Argon2's input is bytes, and a multi-byte password can exceed the library's
# own limit while staying inside the character cap.
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

ACCESS_TOKEN_MAX = 4096
