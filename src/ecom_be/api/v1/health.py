from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from ecom_be.api.deps import Probe, get_database_probe, get_redis_probe
from ecom_be.config.settings import Settings, get_settings
from ecom_be.schemas.health.response import LivenessEnvelope, ReadinessEnvelope
from ecom_be.services.health import HealthService

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessEnvelope)
def liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LivenessEnvelope:
    return LivenessEnvelope(data=HealthService(settings).liveness())


@router.get(
    "/ready",
    response_model=ReadinessEnvelope,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessEnvelope}},
)
async def readiness(
    response: Response,
    database_probe: Annotated[Probe, Depends(get_database_probe)],
    redis_probe: Annotated[Probe, Depends(get_redis_probe)],
) -> ReadinessEnvelope:
    """Report dependency readiness.

    The status code is the signal and the body shape is identical at 200 and at
    503, which is what lets a client read "not ready" as a state rather than as a
    transport failure. Setting ``response.status_code`` is how that is expressed
    without hand-building a response body.
    """

    result = await HealthService().readiness(database_probe, redis_probe)
    if result.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessEnvelope(data=result)
