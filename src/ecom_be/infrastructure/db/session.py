from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ecom_be.config.settings import Settings, get_settings


def create_db_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create an async PostgreSQL engine for one application."""

    app_settings = settings if settings is not None else get_settings()
    return create_async_engine(
        str(app_settings.database_url),
        pool_pre_ping=True,
    )


def create_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create the request-scoped async session factory."""

    return async_sessionmaker(db_engine, expire_on_commit=False)


settings = get_settings()
engine: AsyncEngine = create_db_engine(settings)
SessionFactory: async_sessionmaker[AsyncSession] = create_session_factory(engine)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield one request-scoped session without an implicit commit."""

    async with SessionFactory() as session:
        yield session
