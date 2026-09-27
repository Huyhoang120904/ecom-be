"""merge the identity and catalog migration branches

Revision ID: d5a6e7f8b9c0
Revises: c1f930e42d11, 3c1f9a7d2b40
Create Date: 2026-09-27 00:00:00.000000

The identity/admin-buyer work and the catalog work both branched from the
identity seed revision. This no-op revision makes their shared history a single
upgrade target for fresh databases and for databases already at either branch.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d5a6e7f8b9c0"
down_revision: str | Sequence[str] | None = (
    "c1f930e42d11",
    "3c1f9a7d2b40",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge the two already-complete migration branches."""


def downgrade() -> None:
    """Expose both branch tips again when downgrading past the merge."""
