import asyncio
import logging
from collections.abc import Awaitable, Callable

from ecom_be.config.settings import Settings, get_settings
from ecom_be.schemas.health.response import (
    DependencyName,
    DependencyStatus,
    LivenessResponse,
    ReadinessResponse,
    ReadinessStatus,
)
from ecom_be.utils.health import get_service_name

logger = logging.getLogger(__name__)
Probe = Callable[[], Awaitable[bool]]


class HealthService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings if settings is not None else get_settings()

    def liveness(self) -> LivenessResponse:
        return LivenessResponse(status="ok", service=get_service_name(self._settings))

    async def readiness(
        self,
        database_probe: Probe,
        redis_probe: Probe,
    ) -> ReadinessResponse:
        database_status, redis_status = await asyncio.gather(
            self._run_probe("database", database_probe),
            self._run_probe("redis", redis_probe),
        )
        dependencies: dict[DependencyName, DependencyStatus] = {
            "database": database_status,
            "redis": redis_status,
        }
        status: ReadinessStatus = (
            "ok"
            if all(value == "ok" for value in dependencies.values())
            else "not_ready"
        )
        return ReadinessResponse(status=status, dependencies=dependencies)

    @staticmethod
    async def _run_probe(name: str, probe: Probe) -> DependencyStatus:
        try:
            return "ok" if await probe() else "unavailable"
        except Exception:  # noqa: BLE001 - a failed probe means not ready
            logger.warning("Health readiness probe failed for %s", name)
            return "unavailable"
