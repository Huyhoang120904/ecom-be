"""The single import site that aggregates module ORM models onto ``Base.metadata``.

``alembic/env.py`` sets ``target_metadata`` to ``metadata`` below, and Alembic's
autogenerate compares the live database against exactly that object. A model
class that is never imported here is invisible to it, and
``alembic revision --autogenerate`` silently emits an empty (``pass``-only)
revision.

To add a persisted module (README.md -> Database migrations):

1. Declare the model classes on the shared ``Base`` from
   ``ecom_be.infrastructure.db.base`` in
   ``ecom_be/modules/<module_name>/models.py``.
2. Import those classes in the ``Module model imports`` block below and append
   each class to ``__all__`` -- importing the class is what registers its table
   on the shared metadata.
3. Run ``uv run alembic revision --autogenerate -m "<change>"``.

``tests/unit/test_migration_metadata.py`` fails when a module ships a
``models.py`` that this view does not import, so the aggregation point cannot
drift out of sync with the modules.
"""

from sqlalchemy import MetaData

from ecom_be.infrastructure.db.base import Base

# --- Module model imports ----------------------------------------------------
# Importing the class is what registers its table on the shared metadata, and the
# aggregation guard in tests/unit/test_migration_metadata.py fails when a module's
# models.py is missing from this block.
from ecom_be.modules.identity.models import (
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
