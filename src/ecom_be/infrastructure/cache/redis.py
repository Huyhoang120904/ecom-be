from redis.asyncio import Redis, from_url

from ecom_be.config.settings import Settings, get_settings


def create_redis_client(settings: Settings | None = None) -> Redis:
    """Create one async Redis client for an application lifecycle."""

    app_settings = settings if settings is not None else get_settings()
    return from_url(str(app_settings.redis_url), decode_responses=True)
