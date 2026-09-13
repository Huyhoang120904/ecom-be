"""Public exports of the identity module.

``Principal`` is imported from its own module rather than re-exported through
``api.deps``, so a service can type its parameters without touching FastAPI.
"""

from ecom_be.modules.identity.principal import Principal

__all__ = ["Principal"]
