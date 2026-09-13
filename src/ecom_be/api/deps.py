from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.core.config import Settings, get_settings
from ecom_be.infrastructure.db import session as db_session
from ecom_be.modules.identity import repository, utils
from ecom_be.modules.identity.errors import (
    AccountInactive,
    Forbidden,
    InvalidToken,
    ShopNotAccessible,
)
from ecom_be.modules.identity.principal import Principal

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


def _bearer_token(request: Request) -> str:
    """Read the bearer token, or raise the unauthenticated error.

    A malformed header is treated exactly like a missing one: the client learns that
    authentication is required and nothing about what was wrong with the value.
    """

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise InvalidToken
    return token.strip()


async def get_current_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> Principal:
    """Resolve the bearer token into a principal.

    Authority is read from the database on every request rather than carried in the
    token. That is what makes a revoked membership, a changed role, or a
    deactivation take effect on the caller's very next request instead of whenever
    their access token happens to expire.
    """

    settings: Settings = request.app.state.settings
    claims = utils.decode_access_token(settings, _bearer_token(request))

    try:
        user_id = UUID(claims["sub"])
        shop_id = UUID(claims["sid"])
    except (KeyError, ValueError) as error:
        raise InvalidToken from error

    resolved = await repository.effective_permissions(
        session, user_id=user_id, shop_id=shop_id
    )
    if resolved is None:
        # Three different states collapse into one query result, and they deserve
        # different answers. An inactive account tells the client to stop retrying;
        # an inaccessible shop tells it to pick another.
        user = await repository.get_user(session, user_id)
        if user is None or user.deactivated_at is not None:
            raise AccountInactive
        raise ShopNotAccessible

    user, role, permissions = resolved
    shop = await repository.get_shop(session, shop_id)
    if shop is None:
        raise ShopNotAccessible
    if not shop.is_active:
        # Suspension is an operator action, distinct from deletion: the token is
        # still valid, the shop is just not usable right now.
        raise ShopNotAccessible

    return Principal(
        user_id=str(user.id),
        active_shop_id=str(shop.id),
        email=user.email,
        roles=(role.key,),
        permissions=frozenset(permissions),
        shop_is_active=shop.is_active,
    )


def require_permissions(*keys: str) -> Callable[..., Awaitable[Principal]]:
    """Build a dependency that refuses a principal missing any of ``keys``.

    Missing permission is a 403 rather than a 404: the caller is authenticated and
    the resource exists, they simply may not act on it. Pretending it does not exist
    would make this harder to debug without making it any safer, since the shop is
    already visible to them.
    """

    async def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if not principal.has(*keys):
            raise Forbidden
        return principal

    return dependency


def require_roles(*keys: str) -> Callable[..., Awaitable[Principal]]:
    """Build a dependency that refuses a principal holding none of ``keys``.

    Roles are checked against the role the caller holds in the *active shop*, not
    against permissions. The two are related but not interchangeable: a role is a
    label, and its meaning lives in the permissions granted to it.
    """

    async def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if not principal.has_any_role(*keys):
            raise Forbidden
        return principal

    return dependency


def get_settings_dependency() -> Settings:
    """The validated settings, for routes that need a TTL or an origin."""

    return get_settings()
