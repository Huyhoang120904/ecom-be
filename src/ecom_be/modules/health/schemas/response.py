from typing import Literal

from pydantic import BaseModel, Field

from ecom_be.api.schemas import BaseResponse

DependencyName = Literal["database", "redis"]
DependencyStatus = Literal["ok", "unavailable"]
ReadinessStatus = Literal["ok", "not_ready"]

# The bound exists so the OpenAPI document carries a maximum for every string it
# publishes, which is what ``tests/unit/test_openapi_string_limits.py`` enforces.
# The value is generous: a service name is short by nature.
SERVICE_NAME_MAX = 64


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    service: str = Field(min_length=1, max_length=SERVICE_NAME_MAX)


class ReadinessResponse(BaseModel):
    status: ReadinessStatus
    dependencies: dict[DependencyName, DependencyStatus]


class LivenessEnvelope(BaseResponse[LivenessResponse]): ...


class ReadinessEnvelope(BaseResponse[ReadinessResponse]): ...
