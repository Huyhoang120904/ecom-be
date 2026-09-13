from typing import Literal

from pydantic import BaseModel

DependencyName = Literal["database", "redis"]
DependencyStatus = Literal["ok", "unavailable"]
ReadinessStatus = Literal["ok", "not_ready"]


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    service: str


class ReadinessResponse(BaseModel):
    status: ReadinessStatus
    dependencies: dict[DependencyName, DependencyStatus]
