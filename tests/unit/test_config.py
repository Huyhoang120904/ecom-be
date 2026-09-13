from pathlib import Path

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
