"""The versioned HTTP surface.

``api_router`` composes every feature router under ``/api/v1`` and adds no
behavior of its own: each module owns its paths, its tags, and its dependencies,
and this file only decides what is mounted. The OpenAPI document is served from
``/api/v1/openapi.json`` (see ``app.main``), so everything reachable through
this router is part of the contract frontends generate from.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health, identity, media

api_router = APIRouter()
# Health stays public so a probe needs no credential. Every other route introduced
# from here on is guarded by a dependency from ``api/deps.py``.
api_router.include_router(health.router)
api_router.include_router(identity.router)
api_router.include_router(identity.shops_router)
api_router.include_router(media.router)

router = api_router
