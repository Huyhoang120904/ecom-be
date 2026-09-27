"""Contract: the committed Alembic graph has one upgrade target."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).parents[2]
EXPECTED_HEAD = "d5a6e7f8b9c0"


def test_alembic_migration_graph_has_one_merged_head():
    config = Config(str(REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [EXPECTED_HEAD]
