"""Bounds on a product, its attribute values, its variants and its images."""

PRODUCT_NAME_MIN = 2

PRODUCT_NAME_MAX = 200

PRODUCT_DESCRIPTION_MAX = 5000

VALUE_TEXT_MAX = 500

# Numeric(18, 4): four decimals, and the integer part must fit in 14 digits.
VALUE_NUMBER_ABS_MAX = 10**14 - 1

SKU_CODE_MIN = 1

SKU_CODE_MAX = 64

# Money is a whole number of the smallest VND unit; ``BIGINT`` holds this comfortably.
PRICE_MAX = 10**12

STOCK_MAX = 10**9

# A variant is identified by its option combination. Each pair contributes at most
# 73 characters to ``option_key``, so this cap keeps the key well inside its column.
VARIANT_OPTIONS_MAX = 5

OPTION_KEY_MAX = 512

# A generous ceiling on the attribute values one request may carry.
ATTRIBUTE_VALUES_MAX = 100

PAGE_SIZE_DEFAULT = 20

PAGE_SIZE_MAX = 100

# Per-product image ceilings (a proposal, kept as constants so they are easy to change).
PRODUCT_IMAGES_MAX = 9

VARIANT_IMAGES_MAX = 5

# Product photos are downscaled to fit inside this box, never cropped or enlarged.
PRODUCT_IMAGE_FIT: tuple[int, int] = (1600, 1600)

PRODUCT_IMAGE_PREFIX = "product-images"
