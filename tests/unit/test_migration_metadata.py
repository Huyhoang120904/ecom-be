"""Contract: Alembic autogenerate sees every ORM model through one named view.

A model that is never imported is invisible to ``Base.metadata``, so
``alembic revision --autogenerate`` emits an empty revision. The import site that
aggregates the models is ``ecom_be/models/__init__.py``; it is the location
``alembic/env.py`` and both docs name, and this test fails if a model module
exists that the view does not genuinely import and register.

The aggregation guard is behavioural, not textual: it parses the view's AST for
the modules it actually imports (so a commented-out import line cannot satisfy
it) and then really imports the view, asserting the ORM classes registered on
the shared metadata are exactly the classes the view exports.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SRC_ROOT = REPO_ROOT / "src"
METADATA_VIEW = SRC_ROOT / "ecom_be" / "models" / "__init__.py"
MODELS_DIR = SRC_ROOT / "ecom_be" / "models"
METADATA_VIEW_DOC_PATH = "src/ecom_be/models/__init__.py"
MODELS_PACKAGE = "ecom_be.models"
SHARED_BASE_NAME = "Base"

# ``__init__.py`` is the view itself, not a model module.
NON_MODEL_FILES = {"__init__.py"}


def _module_path(dotted: str) -> Path:
    return SRC_ROOT / Path(*dotted.split("."))


def _module_exists(dotted: str) -> bool:
    path = _module_path(dotted)
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def _discovered_model_modules() -> set[str]:
    """Dotted names of every model module in ``ecom_be/models/``."""
    return {
        f"{MODELS_PACKAGE}.{model_file.stem}"
        for model_file in sorted(MODELS_DIR.glob("*.py"))
        if model_file.name not in NON_MODEL_FILES
    }


def _imported_modules_in_view() -> set[str]:
    """Dotted names of the modules the view really imports.

    Collected from the view's AST, so a commented-out import line is invisible
    here and cannot stand in for a working import the way a substring check
    would let it.
    """
    tree = ast.parse(METADATA_VIEW.read_text(), filename=str(METADATA_VIEW))
    candidates: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            candidates.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            candidates.add(node.module)
            candidates.update(f"{node.module}.{alias.name}" for alias in node.names)
    # Keep only names that resolve to a real module file: this drops imported
    # symbols (``...models.Probe``) while keeping the module they come from.
    return {name for name in candidates if _module_exists(name)}


def _classes_declared_on_the_shared_base(models_file: Path) -> set[str]:
    """Class names in ``models_file`` that subclass the shared declarative Base."""
    tree = ast.parse(models_file.read_text(), filename=str(models_file))
    declared: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if any(
            (isinstance(base, ast.Name) and base.id == SHARED_BASE_NAME)
            or (isinstance(base, ast.Attribute) and base.attr == SHARED_BASE_NAME)
            for base in node.bases
        ):
            declared.add(node.name)
    return declared


def _registered_module_classes() -> set[str]:
    """ORM classes actually registered on the shared metadata by model modules."""
    from ecom_be.infrastructure.db.base import Base

    return {
        mapper.class_.__name__
        for mapper in Base.registry.mappers
        if str(mapper.class_.__module__).startswith(f"{MODELS_PACKAGE}.")
    }


def test_metadata_view_exports_the_shared_base_metadata():
    from ecom_be.infrastructure.db.base import Base
    from ecom_be.models import metadata

    assert metadata is Base.metadata


def test_alembic_env_targets_the_named_metadata_view():
    env_source = (REPO_ROOT / "alembic" / "env.py").read_text()

    assert "from ecom_be.models import metadata" in env_source
    assert "target_metadata = metadata" in env_source


def test_every_model_module_is_imported_and_registered_by_the_metadata_view():
    discovered = _discovered_model_modules()
    imported = _imported_modules_in_view()

    missing = sorted(discovered - imported)
    assert not missing, (
        f"{METADATA_VIEW_DOC_PATH} does not import {missing}; importing the model "
        "class is what registers its table, so autogenerate would emit an empty "
        "revision"
    )

    # Real import of the aggregation view: this is what Alembic autogenerate
    # loads, and it is what must have executed every model module's imports.
    metadata_view = importlib.import_module("ecom_be.models")

    registered = _registered_module_classes()
    assert set(metadata_view.__all__) == registered, (
        f"{METADATA_VIEW_DOC_PATH} exports {sorted(metadata_view.__all__)} but the "
        f"shared metadata holds module ORM classes {sorted(registered)}; the view's "
        "exports and the registered models have drifted apart"
    )

    for dotted in sorted(discovered):
        models_file = _module_path(dotted).with_suffix(".py")
        declared = _classes_declared_on_the_shared_base(models_file)
        assert declared, (
            f"{models_file.relative_to(REPO_ROOT)} declares no class on the shared "
            f"{SHARED_BASE_NAME}; importing it would register nothing with Alembic"
        )
        unregistered = sorted(declared - registered)
        assert not unregistered, (
            f"{models_file.relative_to(REPO_ROOT)} declares {unregistered} on the "
            "shared Base, but the shared metadata does not hold them; they are not "
            "visible to autogenerate"
        )


def test_docs_name_the_metadata_view_by_path():
    for doc_name in ("README.md", "AGENTS.md"):
        assert METADATA_VIEW_DOC_PATH in (REPO_ROOT / doc_name).read_text(), (
            f"{doc_name} does not name the metadata view {METADATA_VIEW_DOC_PATH}"
        )
