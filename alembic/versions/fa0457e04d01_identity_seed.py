"""identity seed

Revision ID: fa0457e04d01
Revises: fcf89444e962
Create Date: 2026-09-13 18:41:00.000000

Seeds the permission vocabulary and the three system roles.

The vocabulary mirrors the CMS's capability navigation plus the tenancy needs, and
nothing beyond them. ``owner`` holds every permission; ``manager`` holds all but
``shop:update`` and ``membership:manage``, which are owner-only; ``viewer`` is
read-only.

Owner-only shop deletion is why ``shop:update`` matters here: a manager cannot
delete the shop, which is the intent.

Every statement is idempotent, so this revision can be re-run against a database
that already has the rows.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa0457e04d01"
down_revision: str | Sequence[str] | None = "fcf89444e962"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("dashboard:read", "Read the operational dashboard"),
    ("products:read", "List and read products"),
    ("products:write", "Create and edit products"),
    ("orders:read", "List and read orders"),
    ("orders:write", "Update order state"),
    ("shop:read", "Read shop settings"),
    ("shop:update", "Change shop settings, including background and deletion"),
    ("membership:read", "See who belongs to the shop"),
    ("membership:manage", "Change who belongs to the shop"),
)

# shop:update and membership:manage are deliberately absent: they are owner-only.
MANAGER_EXCLUDED: tuple[str, ...] = ("shop:update", "membership:manage")

# Stated explicitly rather than matched with a LIKE '%:read' pattern. A pattern
# would silently grant a future permission whose key merely ends in ':read', and
# "read-only" is a product decision that deserves to be written down.
VIEWER_PERMISSIONS: tuple[str, ...] = (
    "dashboard:read",
    "products:read",
    "orders:read",
    "shop:read",
    "membership:read",
)


def upgrade() -> None:
    """Seed the permission vocabulary, the system roles, and their grants."""

    permissions_values = ", ".join(
        f"(gen_random_uuid(), '{key}', '{description}')"
        for key, description in PERMISSIONS
    )
    op.execute(
        f"""
        INSERT INTO permissions (id, key, description)
        VALUES {permissions_values}
        ON CONFLICT (key) DO NOTHING
        """
    )

    # No conflict target: the uniqueness comes from a *partial* index on
    # ``key WHERE shop_id IS NULL``, and a partial index is not a constraint a
    # target can name. This is the price of the partial index, and it is what keeps
    # the statement re-runnable.
    op.execute(
        """
        INSERT INTO roles (id, key, name)
        VALUES
          (gen_random_uuid(), 'owner', 'Owner'),
          (gen_random_uuid(), 'manager', 'Manager'),
          (gen_random_uuid(), 'viewer', 'Viewer')
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.key = 'owner' AND r.shop_id IS NULL
        ON CONFLICT DO NOTHING
        """
    )

    excluded = ", ".join(f"'{key}'" for key in MANAGER_EXCLUDED)
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.key = 'manager' AND r.shop_id IS NULL
          AND p.key NOT IN ({excluded})
        ON CONFLICT DO NOTHING
        """
    )

    viewer_keys = ", ".join(f"'{key}'" for key in VIEWER_PERMISSIONS)
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.key = 'viewer' AND r.shop_id IS NULL AND p.key IN ({viewer_keys})
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove exactly the seeded rows.

    Scoped by key rather than truncating: a shop-scoped role created later must not
    be collateral damage of downgrading this revision. Grants go first, because the
    role and permission rows are what they reference.
    """

    seeded_keys = ", ".join(f"'{key}'" for key, _description in PERMISSIONS)
    seeded_roles = ", ".join(f"'{key}'" for key in ("owner", "manager", "viewer"))

    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE key IN ({seeded_keys}))
           OR role_id IN (SELECT id FROM roles WHERE key IN ({seeded_roles}))
        """
    )
    op.execute(f"DELETE FROM permissions WHERE key IN ({seeded_keys})")
    op.execute(
        f"DELETE FROM roles WHERE key IN ({seeded_roles}) AND shop_id IS NULL"
    )
