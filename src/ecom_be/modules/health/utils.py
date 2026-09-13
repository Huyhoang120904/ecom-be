from ecom_be.core.config import Settings


def get_service_name(settings: Settings) -> str:
    return settings.app_name
