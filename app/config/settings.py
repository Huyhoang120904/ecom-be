from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

# A signing secret shorter than this is not worth the ceremony of having one, and
# refusing it at startup is far cheaper than discovering it in production.
JWT_SECRET_MIN_LENGTH = 32

DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 900
DEFAULT_REFRESH_TOKEN_TTL_SECONDS = 2_592_000
DEFAULT_MAX_UPLOAD_BYTES = 2_097_152


class Settings(BaseSettings):
    app_name: str = "ecom-be"
    environment: str = "development"
    database_url: PostgresDsn
    redis_url: RedisDsn
    cors_origins: tuple[AnyHttpUrl, ...] = ()

    # Required, with no default: a missing secret must refuse startup rather than
    # let the application mint tokens it cannot verify.
    jwt_secret: str = Field(min_length=JWT_SECRET_MIN_LENGTH)

    access_token_ttl_seconds: int = Field(
        default=DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        ge=60,
        le=86_400,
    )
    refresh_token_ttl_seconds: int = Field(
        default=DEFAULT_REFRESH_TOKEN_TTL_SECONDS,
        ge=3600,
    )

    # Media. The root is a local directory by default; the storage adapter is what
    # makes swapping it for object storage a one-file change.
    media_root: Path = Path(".media")
    # Empty means "derive the origin from the request", which keeps local
    # development correct with no configuration.
    media_base_url: AnyHttpUrl | None = None
    max_upload_bytes: int = Field(default=DEFAULT_MAX_UPLOAD_BYTES, ge=1024)

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
