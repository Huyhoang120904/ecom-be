"""Bounds on a shop: its profile text and its derived slug."""

SHOP_NAME_MIN = 2

SHOP_NAME_MAX = 80

SHOP_DESCRIPTION_MAX = 300

SHOP_WEBSITE_MAX = 255

SLUG_MAX = 80

# Room for a "-" and a collision suffix, so appending never overflows the column.
SLUG_BASE_MAX = 72

SLUG_FALLBACK = "shop"
