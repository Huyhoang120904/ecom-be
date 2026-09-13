from ecom_be.config.settings import Settings


def get_service_name(settings: Settings) -> str:
    return settings.app_name
