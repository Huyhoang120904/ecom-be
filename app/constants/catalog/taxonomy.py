"""Bounds on the shared catalog: brands, categories, attributes, options."""

BRAND_NAME_MIN = 1

BRAND_NAME_MAX = 120

CATEGORY_NAME_MIN = 1

CATEGORY_NAME_MAX = 120

# A slug is derived from a name and gets a collision suffix appended.
CATALOG_SLUG_MAX = 120

CATALOG_SLUG_BASE_MAX = 112

CATALOG_SLUG_FALLBACK = "item"

# How deep the category tree may go. Bounds the cycle walk and a sane taxonomy.
CATEGORY_MAX_DEPTH = 6

ATTRIBUTE_KEY_MIN = 2

ATTRIBUTE_KEY_MAX = 64

ATTRIBUTE_NAME_MIN = 1

ATTRIBUTE_NAME_MAX = 80

OPTION_VALUE_MIN = 1

OPTION_VALUE_MAX = 120
