from ecom_be.core.config import Settings, get_settings

from .schemas.response import LivenessResponse
from .utils import get_service_name


class HealthService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings if settings is not None else get_settings()

    def liveness(self) -> LivenessResponse:
        return LivenessResponse(status="ok", service=get_service_name(self._settings))
