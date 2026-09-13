"""Shared pytest configuration for ecom-be tests.

The suite is split by the ``db`` marker. The default run excludes it, so the
committed tests pass with no Docker service running, which is the rule
``AGENTS.md`` sets. Tests that assert real PostgreSQL behaviour are marked ``db``
and run explicitly:

    uv run pytest -q -m db      # requires `docker compose up -d --wait`

A database assertion written against SQLite would prove nothing here: SQLite has no
``citext``, no partial unique index semantics worth trusting, and no
``gen_random_uuid``.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import PostgresDsn, RedisDsn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _database_url_value() -> str:
    return str(
        PostgresDsn.build(
            scheme="postgresql+asyncpg",
            host="localhost",
            port=5432,
            path="ecommerce",
        )
    )


def _redis_url_value() -> str:
    return str(RedisDsn.build(scheme="redis", host="localhost", port=6379, path="0"))


def _migrated_database_url() -> str:
    """The ``DATABASE_URL`` a developer actually migrated.

    Read from ``.env`` directly rather than from ``Settings``, because the autouse
    fixture above exports a placeholder ``DATABASE_URL`` and environment variables
    outrank the dotenv file in pydantic-settings. Using the placeholder here would
    point the ``db`` tests at a database with no migrations applied.
    """

    env_path = Path(__file__).parents[1] / ".env"
    if not env_path.is_file():
        pytest.skip(".env is missing; copy .env.example and run alembic upgrade head")
    for line in env_path.read_text().splitlines():
        entry = line.strip()
        if entry.startswith("DATABASE_URL="):
            return entry.partition("=")[2].strip().strip('"').strip("'")
    pytest.skip(".env declares no DATABASE_URL")


@pytest.fixture(autouse=True)
def configure_settings_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_NAME", "ecom-be")
    monkeypatch.setenv("DATABASE_URL", _database_url_value())
    monkeypatch.setenv("REDIS_URL", _redis_url_value())
    # Required with no default: a missing signing secret refuses startup, so every
    # test that constructs Settings needs one.
    monkeypatch.setenv("JWT_SECRET", "test-secret-that-is-long-enough-32")
    yield

    from ecom_be.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    from ecom_be.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def db_engine() -> AsyncIterator[object]:
    """An engine built from the migrated ``DATABASE_URL``."""

    engine = create_async_engine(_migrated_database_url(), pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    """A session wrapped in a transaction that is always rolled back.

    Each test starts from the same schema and leaves nothing behind, so the
    ``db``-marked tests do not depend on each other's rows or on their order.
    """

    connection = await db_engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest.fixture
async def db_async_client(db_engine) -> AsyncIterator[AsyncClient]:
    """An HTTP client whose application shares ``db_session``'s transaction.

    Overriding the session dependency is what makes a ``db``-marked API test
    coherent: the endpoint writes through the same connection the test reads from,
    so the test sees its own data instead of a stale snapshot.
    """

    from ecom_be.api.deps import get_application_db_session
    from ecom_be.main import app

    engine = create_async_engine(_migrated_database_url(), pool_pre_ping=True)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False)

    async def override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_application_db_session] = override
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_application_db_session, None)
        await transaction.rollback()
        await connection.close()
        await engine.dispose()
