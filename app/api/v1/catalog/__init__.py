"""The catalog HTTP contract, assembled from one module per resource.

Each module carries a ``read_router`` (any authenticated caller) and an
``admin_router`` (``catalog:manage``). ``api/v1`` includes ``router``; nothing else
imports these modules.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.catalog import attributes, brands, categories, category_attributes

router = APIRouter()
for _module in (brands, categories, attributes, category_attributes):
    router.include_router(_module.read_router)
    router.include_router(_module.admin_router)

__all__ = ["router"]
