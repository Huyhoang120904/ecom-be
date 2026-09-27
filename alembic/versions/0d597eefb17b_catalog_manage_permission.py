"""catalog manage permission

Revision ID: 0d597eefb17b
Revises: fa0457e04d01
Create Date: 2026-09-20 10:00:00.000000

Seeds ``catalog:manage``, the permission that guards writes to the shared catalog
(categories, attributes, options, brands).

This is a deliberately *temporary* gate. It is a permission inside a shop, so every
shop ``owner`` holds it and can edit the catalog for the whole marketplace. That is
accepted for this phase because there are no outside sellers yet. The planned
replacement is a platform-admin flag on ``users`` (see ``changes/20-09-2026-
CatalogAndProduct/plan.md``, "Next phase"), after which this permission is removed.

Only ``owner`` is granted it. ``manager`` and ``viewer`` are not, so the seeded
grants of the earlier revision are left untouched. Every statement is idempotent.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0d597eefb17b"
down_revision: str | Sequence[str] | None = "fa0457e04d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_KEY = "catalog:manage"
PERMISSION_DESCRIPTION = (
    "Configure the shared catalog: categories, attributes, options, brands"
)


def upgrade() -> None:
    """Seed the permission and grant it to the system ``owner`` role only."""

    op.execute(
        f"""
        INSERT INTO permissions (id, key, description)
        VALUES (gen_random_uuid(), '{PERMISSION_KEY}', '{PERMISSION_DESCRIPTION}')
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.key = 'owner' AND r.shop_id IS NULL AND p.key = '{PERMISSION_KEY}'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove the permission and every grant of it."""

    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE key = '{PERMISSION_KEY}')
        """
    )
    op.execute(f"DELETE FROM permissions WHERE key = '{PERMISSION_KEY}'")
