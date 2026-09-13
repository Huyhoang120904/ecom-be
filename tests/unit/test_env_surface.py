"""Contract: the application env surface and the compose env surface stay apart.

``Settings`` forbids unknown keys, and ``docker compose`` interpolates the same
working directory. If a compose-only key (``POSTGRES_*``, ``REDIS_PORT``) is
advertised as a ``.env`` entry, a developer who follows the docs breaks
application startup with a ``ValidationError`` that looks unrelated to Compose.
These tests pin the separation so it cannot regress silently.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE_ENV_EXAMPLE = REPO_ROOT / "compose.env.example"
COMPOSE_FILE = REPO_ROOT / "compose.yaml"

APP_KEYS = {"APP_NAME", "ENVIRONMENT", "DATABASE_URL", "REDIS_URL", "CORS_ORIGINS"}
COMPOSE_ONLY_KEYS = {
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_PORT",
    "REDIS_PORT",
}


def _declared_keys(path: Path) -> set[str]:
    """Keys a dotenv file actually sets; comments are ignored."""

    keys: set[str] = set()
    for line in path.read_text().splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        key = entry.partition("=")[0].strip()
        if key:
            keys.add(key)
    return keys


def _offered_keys(path: Path) -> set[str]:
    """Keys a reader can act on, commented or not.

    A commented ``# POSTGRES_PORT=55432`` is still an advertisement: uncommenting
    it is exactly the documented-looking edit that breaks application startup.
    """

    keys: set[str] = set()
    for line in path.read_text().splitlines():
        entry = re.sub(r"^\s*#\s?", "", line).strip()
        if not entry or "=" not in entry:
            continue
        key = entry.partition("=")[0].strip()
        if key.isupper():
            keys.add(key)
    return keys


def _compose_interpolated_keys() -> set[str]:
    """Every ``${VAR`` compose interpolates, i.e. every key a developer may set."""

    return set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", COMPOSE_FILE.read_text()))


def _docker_compose_works() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


def test_env_example_only_declares_keys_the_application_parses():
    from ecom_be.config.settings import Settings

    declared = _declared_keys(ENV_EXAMPLE)

    unknown = {key for key in declared if key.lower() not in Settings.model_fields}
    assert unknown == set(), (
        f".env.example declares keys Settings rejects: {sorted(unknown)}. "
        "A developer who copies them into .env breaks application startup."
    )
    assert not (APP_KEYS - declared), (
        f"missing application keys: {sorted(APP_KEYS - declared)}"
    )


def test_env_example_offers_no_compose_only_key_to_copy():
    offered = _offered_keys(ENV_EXAMPLE)

    assert (offered & COMPOSE_ONLY_KEYS) == set(), (
        ".env.example still offers compose-only keys: "
        f"{sorted(offered & COMPOSE_ONLY_KEYS)}; they belong in compose.env.example"
    )


def test_settings_reject_a_compose_only_key_written_into_the_env_file(
    monkeypatch, tmp_path
):
    """The reported F1 failure: a compose key inside .env is fatal at startup.

    The key must reach ``Settings`` through the parsed env file, not through an
    exported shell variable -- ``pydantic-settings`` only enforces
    ``extra='forbid'`` for the dotenv source, which is precisely why the
    documented "uncomment this block in .env" edit breaks the app.
    """

    from ecom_be.config.settings import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql+asyncpg://localhost:55432/ecommerce\n"
        "REDIS_URL=redis://localhost:56379/0\n"
        "POSTGRES_PORT=55432\n"
    )

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "postgres_port" in str(excinfo.value)


def test_compose_env_example_documents_exactly_the_compose_only_keys():
    assert COMPOSE_ENV_EXAMPLE.is_file(), "the compose env surface has no example file"
    assert _declared_keys(COMPOSE_ENV_EXAMPLE) == COMPOSE_ONLY_KEYS


def test_compose_interpolates_only_keys_documented_in_the_compose_env_surface():
    documented = _declared_keys(COMPOSE_ENV_EXAMPLE)

    undocumented = _compose_interpolated_keys() - documented
    assert undocumented == set(), (
        "compose.yaml interpolates keys absent from compose.env.example: "
        f"{sorted(undocumented)}"
    )
    assert (documented & _declared_keys(ENV_EXAMPLE)) == set(), (
        "the two env surfaces must not overlap"
    )


@pytest.mark.skipif(not _docker_compose_works(), reason="docker compose is unavailable")
def test_compose_env_file_overrides_still_reach_compose_config(tmp_path):
    env_file = tmp_path / "compose.env"
    env_file.write_text("POSTGRES_PORT=55532\nREDIS_PORT=56637\n")

    result = subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "config"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert 'published: "55532"' in result.stdout
    assert 'published: "56637"' in result.stdout
