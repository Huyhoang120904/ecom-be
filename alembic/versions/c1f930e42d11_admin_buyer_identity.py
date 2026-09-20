"""admin and buyer identity migration

Revision ID: c1f930e42d11
Revises: fa0457e04d01
Create Date: 2026-09-20 00:00:00.000000

Supports buyer and platform admin identity:
- Makes memberships.shop_id nullable for platform-level roles
- Adjusts unique indexes on memberships for shop vs platform tenancy
- Adds audience column to refresh_tokens
- Seeds platform permissions and the sys_admin platform role with all permissions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1f930e42d11"
down_revision: str | Sequence[str] | None = "fa0457e04d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("platform:metrics:read", "View all system, sales, and platform metrics"),
    ("platform:shops:read", "View all shops across the platform"),
    ("platform:shops:manage", "Suspend, activate, or update shop status"),
    ("platform:users:read", "List and inspect platform users"),
    ("platform:users:manage", "Deactivate or manage user status"),
)


def upgrade() -> None:
    # 1. Alter memberships.shop_id to be nullable
    op.alter_column(
        "memberships",
        "shop_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # 2. Recreate memberships partial unique index for shop memberships
    op.drop_index(
        "memberships_user_shop_live",
        table_name="memberships",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "memberships_user_shop_live",
        "memberships",
        ["user_id", "shop_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND shop_id IS NOT NULL"),
    )

    # 3. Create platform membership partial unique index (shop_id IS NULL)
    op.create_index(
        "memberships_user_platform_live",
        "memberships",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND shop_id IS NULL"),
    )

    # 4. Add audience column to refresh_tokens
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "audience",
            sa.String(length=32),
            server_default=sa.text("'cms'"),
            nullable=False,
        ),
    )

    # 5. Widen the permission key vocabulary to hierarchical keys.
    # The original constraint accepted exactly two colon-separated segments, which
    # cannot express ``platform:metrics:read``. The replacement accepts one or more
    # segments; the pattern is inlined rather than imported so this revision keeps
    # meaning what it meant when it was written.
    op.drop_constraint("permissions_key_ck", "permissions", type_="check")
    op.create_check_constraint(
        "permissions_key_ck",
        "permissions",
        "key ~ '^[a-z][a-z0-9_]*(:[a-z][a-z0-9_]*)+$'",
    )

    # 6. Seed new platform permissions
    permissions_values = ", ".join(
        f"(gen_random_uuid(), '{key}', '{description}')"
        for key, description in NEW_PERMISSIONS
    )
    op.execute(
        f"""
        INSERT INTO permissions (id, key, description)
        VALUES {permissions_values}
        ON CONFLICT (key) DO NOTHING
        """
    )

    # 7. Seed sys_admin role
    op.execute(
        """
        INSERT INTO roles (id, key, name, shop_id)
        VALUES (gen_random_uuid(), 'sys_admin', 'System Administrator', NULL)
        ON CONFLICT DO NOTHING
        """
    )

    # 8. Grant sys_admin all permissions (platform + shop)
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.key = 'sys_admin' AND r.shop_id IS NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    # 1. Remove sys_admin role_permissions and role
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id IN (
            SELECT id FROM roles WHERE key = 'sys_admin' AND shop_id IS NULL
        )
        """
    )
    op.execute(
        """
        DELETE FROM roles WHERE key = 'sys_admin' AND shop_id IS NULL
        """
    )

    # 2. Remove seeded platform permissions
    perm_keys = ", ".join(f"'{key}'" for key, _ in NEW_PERMISSIONS)
    op.execute(
        f"""
        DELETE FROM permissions WHERE key IN ({perm_keys})
        """
    )

    # 3. Restore the original two-segment permission key vocabulary. This runs after
    # the platform rows are gone, because they would violate the narrower constraint.
    op.drop_constraint("permissions_key_ck", "permissions", type_="check")
    op.create_check_constraint(
        "permissions_key_ck",
        "permissions",
        "key ~ '^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$'",
    )

    # 4. Drop audience column from refresh_tokens
    op.drop_column("refresh_tokens", "audience")

    # 5. Drop platform membership unique index
    op.drop_index(
        "memberships_user_platform_live",
        table_name="memberships",
        postgresql_where=sa.text("deleted_at IS NULL AND shop_id IS NULL"),
    )

    # 6. Restore shop membership unique index
    op.drop_index(
        "memberships_user_shop_live",
        table_name="memberships",
        postgresql_where=sa.text("deleted_at IS NULL AND shop_id IS NOT NULL"),
    )
    op.create_index(
        "memberships_user_shop_live",
        "memberships",
        ["user_id", "shop_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 7. Restore memberships.shop_id NOT NULL
    op.alter_column(
        "memberships",
        "shop_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
