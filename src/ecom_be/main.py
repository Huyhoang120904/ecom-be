from fastapi import FastAPI

from ecom_be.api.router import api_router
from ecom_be.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings if settings is not None else get_settings()
    application = FastAPI(
        title=app_settings.app_name,
        openapi_url="/api/v1/openapi.json",
    )
    application.include_router(api_router)
    return application


app = create_app()
