from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from ecom_be.api.deps import Probe, get_database_probe, get_redis_probe
from ecom_be.core.config import Settings, get_settings

from .schemas.response import LivenessResponse, ReadinessResponse
from .services import HealthService

router = APIRouter(prefix="/health", tags=["health"])


def _as_probe(candidate: Probe | bool) -> Probe:
    """Normalize real probes and simple test override results."""

    if callable(candidate):
        return candidate

    async def probe() -> bool:
        return candidate

    return probe


@router.get("/live", response_model=LivenessResponse)
def liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LivenessResponse:
    return HealthService(settings).liveness()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(
    database_probe: Annotated[Probe, Depends(get_database_probe)],
    redis_probe: Annotated[Probe, Depends(get_redis_probe)],
) -> ReadinessResponse | JSONResponse:
    result = await HealthService().readiness(
        _as_probe(database_probe),
        _as_probe(redis_probe),
    )
    if result.status == "not_ready":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=result.model_dump(),
        )
    return result
