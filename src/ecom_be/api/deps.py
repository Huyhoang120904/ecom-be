from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.infrastructure.db import session as db_session

get_db_session = db_session.get_db_session

Probe = Callable[[], Awaitable[bool]]


async def get_application_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a session from the factory owned by the current application."""

    session_factory = getattr(
        request.app.state, "db_session_factory", db_session.SessionFactory
    )
    async with session_factory() as session:
        yield session


async def get_redis_client(request: Request) -> Redis:
    """Return the Redis client owned by the application lifecycle."""

    client: Redis | None = getattr(request.app.state, "redis_client", None)
    if client is None:
        client = getattr(request.app.state, "redis", None)
    if client is None:
        raise RuntimeError("Redis client is not initialized")
    return client


async def database_probe(session: AsyncSession) -> bool:
    """Check database availability with a minimal read-only query."""

    await session.execute(text("SELECT 1"))
    return True


async def redis_probe(client: Redis) -> bool:
    """Check Redis availability with its asynchronous ping command."""

    return bool(await client.ping())


def get_database_probe(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Probe:
    """Build a database probe using the request's database session."""

    async def probe() -> bool:
        return await database_probe(session)

    return probe


def get_redis_probe(
    client: Annotated[Redis, Depends(get_redis_client)],
) -> Probe:
    """Build a Redis probe using the lifecycle-owned client."""

    async def probe() -> bool:
        return await redis_probe(client)

    return probe
