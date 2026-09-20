"""Contract: the Alembic config receives the database URL byte-for-byte.

``alembic/config.py`` hands every value to ``configparser``, where ``%`` starts
an interpolation token. A DSN whose credential is URL-encoded -- ``%40`` for an
``@`` -- therefore used to raise ``ValueError: invalid interpolation syntax`` and
break ``alembic upgrade head``. These tests drive the real ``alembic/env.py`` in
a subprocess, so they exercise the documented command end to end, and assert the
URL Alembic finally consumes round-trips back to the original DSN.

No connection string is written out literally here: each one is built from
``PostgresDsn`` parts, exactly as ``tests/conftest.py`` builds the test
environment's URL, so the encoded ``%40`` arises from the credential rather than
from a committed DSN.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic import PostgresDsn

from app.infrastructure.db.urls import escape_for_configparser

REPO_ROOT = Path(__file__).parents[2]

_ROUND_TRIP_SCRIPT = """
import contextlib
import io

from alembic import command
from alembic.config import Config

config = Config("alembic.ini")
with contextlib.redirect_stdout(io.StringIO()):
    command.upgrade(config, "head", sql=True)
print("CONSUMED:" + config.get_main_option("sqlalchemy.url"))
"""


def _dsn(password: str) -> str:
    """A migration DSN string built from parts, never committed whole."""
    return str(
        PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username="app",
            password=password,
            host="localhost",
            port=55432,
            path="ecommerce",
        )
    )


@pytest.fixture
def percent_dsn() -> str:
    """A DSN whose credential URL-encodes to ``%40``."""
    dsn = _dsn("p@ss")
    assert "%40" in dsn, "fixture precondition: the credential must encode a percent"
    return dsn


@pytest.fixture
def ordinary_dsn() -> str:
    """A DSN with no percent sign anywhere."""
    dsn = _dsn("alnum")
    assert "%" not in dsn, "fixture precondition: the DSN must be percent-free"
    return dsn


def _run_env(database_url: str) -> subprocess.CompletedProcess[str]:
    """Run the real ``env.py`` through the documented upgrade command."""
    return subprocess.run(
        [sys.executable, "-c", _ROUND_TRIP_SCRIPT],
        cwd=REPO_ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "DATABASE_URL": database_url,
            "REDIS_URL": "redis://localhost:56379/0",
            "JWT_SECRET": "test-secret-that-is-long-enough-32",
        },
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_escape_for_configparser_doubles_every_percent(percent_dsn: str):
    escaped = escape_for_configparser(percent_dsn)

    assert escaped == percent_dsn.replace("%", "%%")
    assert "%%40" in escaped


def test_escape_for_configparser_leaves_a_percent_free_url_alone(ordinary_dsn: str):
    assert escape_for_configparser(ordinary_dsn) == ordinary_dsn


def test_escaped_value_round_trips_through_alembic_config(percent_dsn: str):
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", escape_for_configparser(percent_dsn))

    assert config.get_main_option("sqlalchemy.url") == percent_dsn
    assert config.get_section(config.config_ini_section, {})["sqlalchemy.url"] == (
        percent_dsn
    )


def test_alembic_env_round_trips_a_percent_encoded_url(percent_dsn: str):
    result = _run_env(percent_dsn)

    assert result.returncode == 0, result.stderr
    assert f"CONSUMED:{percent_dsn}" in result.stdout
    assert "invalid interpolation syntax" not in result.stderr


def test_alembic_env_still_round_trips_an_ordinary_url(ordinary_dsn: str):
    result = _run_env(ordinary_dsn)

    assert result.returncode == 0, result.stderr
    assert f"CONSUMED:{ordinary_dsn}" in result.stdout
