def test_settings_read_database_and_redis_urls(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/ecommerce"
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    from ecom_be.core.config import Settings

    settings = Settings()

    assert settings.database_url.scheme == "postgresql+asyncpg"
    assert str(settings.redis_url) == "redis://localhost:6379/0"


def test_settings_read_application_and_cors_values(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Ecommerce API")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/ecommerce"
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
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
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/ecommerce"
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    from ecom_be.core.config import get_settings

    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    get_settings.cache_clear()

    assert first is second
