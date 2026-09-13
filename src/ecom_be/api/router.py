from fastapi import APIRouter

from ecom_be.modules.health.router import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)

router = api_router
