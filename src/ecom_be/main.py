from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ecom_be.api.deps import get_application_db_session
from ecom_be.api.router import api_router
from ecom_be.core.config import Settings, get_settings
from ecom_be.core.errors import register_exception_handlers
from ecom_be.core.logging import configure_logging
from ecom_be.infrastructure.cache.redis import create_redis_client
from ecom_be.infrastructure.db.session import (
    SessionFactory,
    create_db_engine,
    create_session_factory,
    engine,
    get_db_session,
)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Own shared external-service clients for the application lifetime."""

    redis_client = create_redis_client(application.state.settings)
    application.state.redis_client = redis_client
    application.state.redis = redis_client
    try:
        yield
    finally:
        try:
            await redis_client.aclose()
        finally:
            await application.state.db_engine.dispose()


def _cors_origins(settings: Settings) -> list[str]:
    origins = [str(origin).rstrip("/") for origin in settings.cors_origins]
    if "*" in origins:
        raise ValueError("Wildcard CORS origins cannot be used with credentials")
    return origins


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    app_settings = settings if settings is not None else get_settings()
    db_engine = engine if settings is None else create_db_engine(app_settings)
    session_factory = (
        SessionFactory if settings is None else create_session_factory(db_engine)
    )

    application = FastAPI(
        title=app_settings.app_name,
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(app_settings),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(application)
    application.state.settings = app_settings
    application.state.db_engine = db_engine
    application.state.db_session_factory = session_factory
    application.dependency_overrides[get_settings] = lambda: app_settings
    application.dependency_overrides[get_db_session] = get_application_db_session
    application.include_router(api_router)
    return application


app = create_app()
