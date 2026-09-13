"""Contract: Alembic autogenerate sees module ORM models through one named view.

A model that is never imported is invisible to ``Base.metadata``, so
``alembic revision --autogenerate`` emits an empty revision. The import site
that aggregates module models is ``ecom_be/infrastructure/db/models.py``; it is
the location ``alembic/env.py`` and both docs name, and this test fails if a
module gains a ``models.py`` that the view does not import.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
METADATA_VIEW = REPO_ROOT / "src" / "ecom_be" / "infrastructure" / "db" / "models.py"
MODULES_DIR = REPO_ROOT / "src" / "ecom_be" / "modules"
METADATA_VIEW_DOC_PATH = "src/ecom_be/infrastructure/db/models.py"


def test_metadata_view_exports_the_shared_base_metadata():
    from ecom_be.infrastructure.db.base import Base
    from ecom_be.infrastructure.db.models import metadata

    assert metadata is Base.metadata


def test_alembic_env_targets_the_named_metadata_view():
    env_source = (REPO_ROOT / "alembic" / "env.py").read_text()

    assert "from ecom_be.infrastructure.db.models import metadata" in env_source
    assert "target_metadata = metadata" in env_source


def test_every_module_models_file_is_imported_by_the_metadata_view():
    view_source = METADATA_VIEW.read_text()

    for models_file in sorted(MODULES_DIR.glob("*/models.py")):
        module_name = models_file.parent.name
        qualified = f"ecom_be.modules.{module_name}.models"
        assert qualified in view_source, (
            f"{models_file.relative_to(REPO_ROOT)} is not imported by "
            f"{METADATA_VIEW_DOC_PATH}; autogenerate would emit an empty revision"
        )


def test_docs_name_the_metadata_view_by_path():
    for doc_name in ("README.md", "AGENTS.md"):
        assert METADATA_VIEW_DOC_PATH in (REPO_ROOT / doc_name).read_text(), (
            f"{doc_name} does not name the metadata view {METADATA_VIEW_DOC_PATH}"
        )
