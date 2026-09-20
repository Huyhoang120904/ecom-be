"""Every identity bound, grouped by the subject it governs.

The package re-exports all of them, so ``from app.constants.identity import
EMAIL_MAX`` keeps working and a caller never needs to know which subject module
a bound lives in. ``__all__`` is spelled out because ``no_implicit_reexport``
makes an unlisted re-export a type error.
"""

from app.constants.identity.account import (
    ACCESS_TOKEN_MAX,
    BIO_MAX,
    EMAIL_MAX,
    EMAIL_MIN,
    FULL_NAME_MAX,
    FULL_NAME_MIN,
    JOB_TITLE_MAX,
    PASSWORD_MAX,
    PASSWORD_MAX_BYTES,
    PASSWORD_MIN,
    PHONE_MAX_DIGITS,
    PHONE_MAX_INPUT,
    PHONE_MIN_DIGITS,
)
from app.constants.identity.media import (
    MEDIA_KEY_MAX,
    UPLOAD_FIELD_NAME,
    URL_MAX,
)
from app.constants.identity.rbac import (
    PERMISSION_DESCRIPTION_MAX,
    PERMISSION_KEY_MAX,
    ROLE_KEY_MAX,
    ROLE_NAME_MAX,
)
from app.constants.identity.shop import (
    SHOP_DESCRIPTION_MAX,
    SHOP_NAME_MAX,
    SHOP_NAME_MIN,
    SHOP_WEBSITE_MAX,
    SLUG_BASE_MAX,
    SLUG_FALLBACK,
    SLUG_MAX,
)

__all__ = [
    "ACCESS_TOKEN_MAX",
    "BIO_MAX",
    "EMAIL_MAX",
    "EMAIL_MIN",
    "FULL_NAME_MAX",
    "FULL_NAME_MIN",
    "JOB_TITLE_MAX",
    "MEDIA_KEY_MAX",
    "PASSWORD_MAX",
    "PASSWORD_MAX_BYTES",
    "PASSWORD_MIN",
    "PERMISSION_DESCRIPTION_MAX",
    "PERMISSION_KEY_MAX",
    "PHONE_MAX_DIGITS",
    "PHONE_MAX_INPUT",
    "PHONE_MIN_DIGITS",
    "ROLE_KEY_MAX",
    "ROLE_NAME_MAX",
    "SHOP_DESCRIPTION_MAX",
    "SHOP_NAME_MAX",
    "SHOP_NAME_MIN",
    "SHOP_WEBSITE_MAX",
    "SLUG_BASE_MAX",
    "SLUG_FALLBACK",
    "SLUG_MAX",
    "UPLOAD_FIELD_NAME",
    "URL_MAX",
]
