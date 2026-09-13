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

import os
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


# The environment is established here, at import, rather than inside a fixture.
#
# ``ecom_be.main`` builds its module-level ``app`` -- and therefore
# ``app.state.settings`` -- at import time, which happens during test *collection*,
# before any fixture runs. A fixture that later injected a different ``JWT_SECRET``
# would leave ``get_settings()`` disagreeing with the app: a token signed by the
# service would fail signature verification in the guard, because the two sides
# would be using different secrets. That mismatch is invisible in a single-file run
# and only surfaces when the whole suite shares a process.
os.environ.setdefault("APP_NAME", "ecom-be")
os.environ.setdefault("DATABASE_URL", _database_url_value())
os.environ.setdefault("REDIS_URL", _redis_url_value())
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-32")


def _migrated_database_url() -> str:
    """The ``DATABASE_URL`` a developer actually migrated.

    Read from ``.env`` directly rather than from the settings object, because the
    test environment deliberately exports a placeholder ``DATABASE_URL`` (above) so
    the committed suite needs no Docker. The ``db`` tests are the exception: they
    should point at the migrated compose database, not at the placeholder.
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
def clear_settings_cache():
    """Keep the cached settings from leaking one test's environment into the next."""

    from ecom_be.core.config import get_settings

    yield
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
    """An HTTP client whose application shares a transaction and skips rate limiting.

    Two overrides, for two different reasons:

    * The session, so the endpoint writes through the same connection the test reads
      from and therefore sees its own data rather than a stale snapshot.
    * The Redis client for rate limiting, because a shared counter in a real Redis is
      cross-test state: enough logins across a suite trip the limit and later tests
      start failing with a 429 that has nothing to do with what they assert.
      ``None`` means "no limiting", which the limiter already treats as fail-open.
    """

    from ecom_be.api.deps import get_application_db_session, get_optional_redis_client
    from ecom_be.main import app

    engine = create_async_engine(_migrated_database_url(), pool_pre_ping=True)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    async def no_redis():
        return None

    app.dependency_overrides[get_application_db_session] = override_session
    app.dependency_overrides[get_optional_redis_client] = no_redis
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_application_db_session, None)
        app.dependency_overrides.pop(get_optional_redis_client, None)
        await transaction.rollback()
        await connection.close()
        await engine.dispose()
