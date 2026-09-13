"""Shared pytest configuration for ecom-be tests."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import PostgresDsn, RedisDsn


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


@pytest.fixture(autouse=True)
def configure_settings_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_NAME", "ecom-be")
    monkeypatch.setenv("DATABASE_URL", _database_url_value())
    monkeypatch.setenv("REDIS_URL", _redis_url_value())
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
