"""The single import site that aggregates ORM models onto ``Base.metadata``.

``alembic/env.py`` sets ``target_metadata`` to ``metadata`` below, and Alembic's
autogenerate compares the live database against exactly that object. A model
class that is never imported here is invisible to it, and
``alembic revision --autogenerate`` silently emits an empty (``pass``-only)
revision.

To add a persisted feature (README.md -> Database migrations):

1. Declare the model classes on the shared ``Base`` from
   ``ecom_be.infrastructure.db.base`` in ``ecom_be/models/<feature>.py``.
2. Import those classes in the ``Feature model imports`` block below and append
   each class to ``__all__`` -- importing the class is what registers its table
   on the shared metadata.
3. Run ``uv run alembic revision --autogenerate -m "<change>"``.

``tests/unit/test_migration_metadata.py`` fails when a model module exists that
this view does not import, so the aggregation point cannot drift out of sync
with ``ecom_be/models/``.
"""

from sqlalchemy import MetaData

from ecom_be.infrastructure.db.base import Base

# --- Feature model imports ---------------------------------------------------
# Importing the class is what registers its table on the shared metadata, and the
# aggregation guard in tests/unit/test_migration_metadata.py fails when a model
# module is missing from this block.
from ecom_be.models.identity import (
    Membership,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    Shop,
    User,
)

__all__: list[str] = [
    "Membership",
    "Permission",
    "RefreshToken",
    "Role",
    "RolePermission",
    "Shop",
    "User",
]

# Handed to Alembic as ``target_metadata``. Every model imported above lands on
# this same object because they all share the one declarative ``Base``.
metadata: MetaData = Base.metadata
