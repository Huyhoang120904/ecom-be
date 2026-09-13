from typing import Annotated

from fastapi import APIRouter, Depends

from ecom_be.core.config import Settings, get_settings

from .schemas.response import LivenessResponse
from .services import HealthService

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
def liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LivenessResponse:
    return HealthService(settings).liveness()
