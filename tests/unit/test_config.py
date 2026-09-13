from pathlib import Path

import pytest
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


def test_settings_read_database_and_redis_urls(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _database_url_value())
    monkeypatch.setenv("REDIS_URL", _redis_url_value())

    from ecom_be.core.config import Settings

    settings = Settings()

    assert settings.database_url.scheme == "postgresql+asyncpg"
    assert str(settings.redis_url) == _redis_url_value()


def test_jwt_secret_is_required(monkeypatch, tmp_path):
    """A missing signing secret must refuse startup, not mint unverifiable tokens.

    ``chdir`` to an empty directory is what isolates this from the developer's own
    ``.env``: without it the assertion would pass or fail depending on whether a
    secret happens to be present locally, which is not a test of anything.
    """

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", _database_url_value())
    monkeypatch.setenv("REDIS_URL", _redis_url_value())
    monkeypatch.delenv("JWT_SECRET", raising=False)

    from pydantic import ValidationError

    from ecom_be.core.config import Settings

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "jwt_secret" in str(excinfo.value)


def test_jwt_secret_must_be_long_enough(monkeypatch):
    """A short secret is a weakness, and it is cheapest to refuse it at startup."""

    monkeypatch.setenv("DATABASE_URL", _database_url_value())
    monkeypatch.setenv("REDIS_URL", _redis_url_value())
    monkeypatch.setenv("JWT_SECRET", "too-short")

    from pydantic import ValidationError

    from ecom_be.core.config import Settings

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "jwt_secret" in str(excinfo.value)


def test_jwt_secret_at_the_minimum_length_is_accepted(monkeypatch):
    from ecom_be.core.config import Settings

    monkeypatch.setenv("DATABASE_URL", _database_url_value())
    monkeypatch.setenv("REDIS_URL", _redis_url_value())
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    assert Settings().jwt_secret == "x" * 32


def test_token_ttls_and_media_settings_have_documented_defaults(monkeypatch):
    from ecom_be.core.config import Settings

    monkeypatch.setenv("DATABASE_URL", _database_url_value())
    monkeypatch.setenv("REDIS_URL", _redis_url_value())
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    settings = Settings()

    assert settings.access_token_ttl_seconds == 900
    assert settings.refresh_token_ttl_seconds == 2_592_000
    assert settings.max_upload_bytes == 2_097_152
    assert settings.media_root.name == ".media"
    assert settings.media_base_url is None


def test_env_example_declares_the_new_settings_with_placeholders():
    """The new keys are application settings, so they belong in .env.example."""

    example_path = Path(__file__).parents[2] / ".env.example"
    values = {
        key: value
        for line in example_path.read_text().splitlines()
        if (key := line.partition("=")[0])
        for value in [line.partition("=")[2]]
    }

    assert values["JWT_SECRET"].startswith("<")
    assert values["ACCESS_TOKEN_TTL_SECONDS"] == "900"
    assert values["REFRESH_TOKEN_TTL_SECONDS"] == "2592000"


def test_settings_read_application_and_cors_values(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Ecommerce API")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", _database_url_value())
    monkeypatch.setenv("REDIS_URL", _redis_url_value())
    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["http://localhost:3000", "https://shop.example.com"]',
    )

    from ecom_be.core.config import Settings

    settings = Settings()

    assert settings.app_name == "Ecommerce API"
    assert settings.environment == "test"
    assert tuple(str(origin) for origin in settings.cors_origins) == (
        "http://localhost:3000/",
        "https://shop.example.com/",
    )


def test_get_settings_returns_cached_instance(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _database_url_value())
    monkeypatch.setenv("REDIS_URL", _redis_url_value())

    from ecom_be.core.config import get_settings

    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    get_settings.cache_clear()

    assert first is second


def test_env_example_contains_replaceable_url_placeholders():
    example_path = Path(__file__).parents[2] / ".env.example"
    values = {
        key: value
        for line in example_path.read_text().splitlines()
        if (key := line.partition("=")[0])
        for value in [line.partition("=")[2]]
    }

    assert values["DATABASE_URL"] == "<replace-with-local-postgresql-url>"
    assert values["REDIS_URL"] == "<replace-with-local-redis-url>"
