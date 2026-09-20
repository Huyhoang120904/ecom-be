"""Health and readiness routes.

Liveness is public and I/O-free. Readiness reports each dependency and stays
``200`` with the same body when everything is up; the readiness route sets ``503``
on the ``Response`` and the envelope echoes it, so the body a client already has
carries the outcome rather than it having to be inferred from the status line alone.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import Probe, get_database_probe, get_redis_probe
from app.config.settings import Settings, get_settings
from app.schemas.common import BaseResponse
from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=BaseResponse[LivenessResponse])
def liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BaseResponse[LivenessResponse]:
    return BaseResponse[LivenessResponse](
        status_code=status.HTTP_200_OK,
        data=HealthService(settings).liveness(),
    )


@router.get(
    "/ready",
    response_model=BaseResponse[ReadinessResponse],
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": BaseResponse[ReadinessResponse],
        }
    },
)
async def readiness(
    response: Response,
    database_probe: Annotated[Probe, Depends(get_database_probe)],
    redis_probe: Annotated[Probe, Depends(get_redis_probe)],
) -> BaseResponse[ReadinessResponse]:
    """Report dependency readiness.

    The body shape is identical at 200 and at 503, which is what lets a client read
    "not ready" as a state rather than as a transport failure. Setting
    ``response.status_code`` is how the status is expressed without hand-building a
    body, and ``status_code`` in the envelope is set from the same decision so the
    two can never disagree.
    """

    result = await HealthService().readiness(database_probe, redis_probe)
    code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if result.status == "not_ready"
        else status.HTTP_200_OK
    )
    response.status_code = code
    return BaseResponse[ReadinessResponse](status_code=code, data=result)
