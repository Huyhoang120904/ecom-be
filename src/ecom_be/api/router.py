from fastapi import APIRouter

from ecom_be.modules.health.router import router as health_router
from ecom_be.modules.identity.router import router as identity_router
from ecom_be.modules.identity.router import shops_router as identity_shops_router
from ecom_be.modules.media.router import router as media_router

api_router = APIRouter()
# Health stays public so a probe needs no credential. Every other route introduced
# from here on is guarded by a dependency from ``api/deps.py``.
api_router.include_router(health_router)
api_router.include_router(identity_router)
api_router.include_router(identity_shops_router)
api_router.include_router(media_router)

router = api_router
