"""catalog seed

Revision ID: 3c1f9a7d2b40
Revises: b8a284382dfb
Create Date: 2026-09-20 16:30:00.000000

Seeds a small, realistic catalog so the product flow can be demonstrated end to end:

* Thời trang > Nam > Áo thun: Size and Color (both required, both variations) and an
  optional Material.
* Điện tử > Máy tính > Laptop: RAM and Storage (required variations), a required CPU,
  an optional Screen size and an optional Color.
* Điện tử > Điện thoại: Color and Storage (required variations), a required RAM and
  an optional Chipset.

Nothing here is a business rule: it is sample reference data that an admin can change
through the catalog API. Every statement is idempotent (``ON CONFLICT DO NOTHING``), so
the revision can be re-run. ``downgrade`` removes exactly these rows, and a row that
products already reference is left in place rather than failing the downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c1f9a7d2b40"
down_revision: str | Sequence[str] | None = "b8a284382dfb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BRANDS: tuple[tuple[str, str], ...] = (
    ("Nike", "nike"),
    ("Adidas", "adidas"),
    ("Uniqlo", "uniqlo"),
    ("Apple", "apple"),
    ("Samsung", "samsung"),
    ("Dell", "dell"),
)

# (slug, name, parent slug). Parents come before their children.
CATEGORIES: tuple[tuple[str, str, str | None], ...] = (
    ("thoi-trang", "Thời trang", None),
    ("thoi-trang-nam", "Nam", "thoi-trang"),
    ("ao-thun", "Áo thun", "thoi-trang-nam"),
    ("dien-tu", "Điện tử", None),
    ("may-tinh", "Máy tính", "dien-tu"),
    ("laptop", "Laptop", "may-tinh"),
    ("dien-thoai", "Điện thoại", "dien-tu"),
)

# (key, name, data type, options)
ATTRIBUTES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("color", "Color", "SELECT", ("Black", "White", "Red", "Blue", "Gray")),
    ("size", "Size", "SELECT", ("S", "M", "L", "XL")),
    ("material", "Material", "TEXT", ()),
    ("ram", "RAM", "SELECT", ("4GB", "8GB", "16GB", "32GB", "64GB")),
    ("storage", "Storage", "SELECT", ("128GB", "256GB", "512GB", "1TB", "2TB")),
    ("cpu", "CPU", "TEXT", ()),
    ("screen_size", "Screen size (inch)", "NUMBER", ()),
    ("chipset", "Chipset", "TEXT", ()),
)

# (category slug, attribute key, required, is_variation, position)
CATEGORY_ATTRIBUTES: tuple[tuple[str, str, bool, bool, int], ...] = (
    ("ao-thun", "size", True, True, 0),
    ("ao-thun", "color", True, True, 1),
    ("ao-thun", "material", False, False, 2),
    ("laptop", "ram", True, True, 0),
    ("laptop", "storage", True, True, 1),
    ("laptop", "cpu", True, False, 2),
    ("laptop", "screen_size", False, False, 3),
    ("laptop", "color", False, False, 4),
    ("dien-thoai", "color", True, True, 0),
    ("dien-thoai", "storage", True, True, 1),
    ("dien-thoai", "ram", True, False, 2),
    ("dien-thoai", "chipset", False, False, 3),
)


def upgrade() -> None:
    """Seed brands, the category tree, attributes, options and their wiring."""

    bind = op.get_bind()

    for name, slug in BRANDS:
        bind.execute(
            sa.text(
                "INSERT INTO brands (id, name, slug) "
                "VALUES (gen_random_uuid(), :name, :slug) ON CONFLICT DO NOTHING"
            ),
            {"name": name, "slug": slug},
        )

    for position, (slug, name, parent) in enumerate(CATEGORIES):
        bind.execute(
            sa.text(
                "INSERT INTO categories (id, parent_id, name, slug, position) "
                "VALUES (gen_random_uuid(), "
                "(SELECT id FROM categories WHERE slug = :parent), "
                ":name, :slug, :position) ON CONFLICT (slug) DO NOTHING"
            ),
            {"parent": parent, "name": name, "slug": slug, "position": position},
        )

    for key, name, data_type, options in ATTRIBUTES:
        bind.execute(
            sa.text(
                "INSERT INTO attributes (id, key, name, data_type) "
                "VALUES (gen_random_uuid(), :key, :name, :data_type) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"key": key, "name": name, "data_type": data_type},
        )
        for sort_order, value in enumerate(options):
            bind.execute(
                sa.text(
                    "INSERT INTO attribute_options "
                    "(id, attribute_id, value, sort_order) "
                    "VALUES (gen_random_uuid(), "
                    "(SELECT id FROM attributes WHERE key = :key), :value, :sort) "
                    "ON CONFLICT (attribute_id, value) DO NOTHING"
                ),
                {"key": key, "value": value, "sort": sort_order},
            )

    for category, key, required, is_variation, position in CATEGORY_ATTRIBUTES:
        bind.execute(
            sa.text(
                "INSERT INTO category_attributes "
                "(category_id, attribute_id, required, is_variation, position) "
                "VALUES ((SELECT id FROM categories WHERE slug = :category), "
                "(SELECT id FROM attributes WHERE key = :key), "
                ":required, :is_variation, :position) ON CONFLICT DO NOTHING"
            ),
            {
                "category": category,
                "key": key,
                "required": required,
                "is_variation": is_variation,
                "position": position,
            },
        )


def downgrade() -> None:
    """Remove the seeded rows, leaving alone any that products already use."""

    bind = op.get_bind()
    slugs = [slug for slug, _, _ in CATEGORIES]
    keys = [key for key, _, _, _ in ATTRIBUTES]

    bind.execute(
        sa.text(
            "DELETE FROM category_attributes WHERE category_id IN "
            "(SELECT id FROM categories WHERE slug = ANY(:slugs))"
        ),
        {"slugs": slugs},
    )
    # Children before parents: the parent foreign key is RESTRICT.
    for slug in reversed(slugs):
        bind.execute(
            sa.text(
                "DELETE FROM categories c WHERE c.slug = :slug "
                "AND NOT EXISTS (SELECT 1 FROM categories k WHERE k.parent_id = c.id) "
                "AND NOT EXISTS (SELECT 1 FROM products p WHERE p.category_id = c.id)"
            ),
            {"slug": slug},
        )
    for key in keys:
        bind.execute(
            sa.text(
                "DELETE FROM attributes a WHERE a.key = :key "
                "AND NOT EXISTS (SELECT 1 FROM category_attributes ca "
                "WHERE ca.attribute_id = a.id) "
                "AND NOT EXISTS (SELECT 1 FROM product_attribute_values v "
                "WHERE v.attribute_id = a.id) "
                "AND NOT EXISTS (SELECT 1 FROM product_variant_options o "
                "WHERE o.attribute_id = a.id)"
            ),
            {"key": key},
        )
    for _, slug in BRANDS:
        bind.execute(
            sa.text(
                "DELETE FROM brands b WHERE b.slug = :slug "
                "AND NOT EXISTS (SELECT 1 FROM products p WHERE p.brand_id = b.id)"
            ),
            {"slug": slug},
        )
