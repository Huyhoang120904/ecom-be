from functools import lru_cache

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ecom-be"
    environment: str = "development"
    database_url: PostgresDsn
    redis_url: RedisDsn
    cors_origins: tuple[AnyHttpUrl, ...] = ()

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
