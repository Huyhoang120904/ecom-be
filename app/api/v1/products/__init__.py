"""The seller-facing product HTTP contract, one module per resource.

``api/v1`` includes ``router``; nothing else imports these modules. Every route is
scoped to the caller's active shop, taken from the token and never from the request.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.products import images, products, variants

router = APIRouter()
for _module in (products, variants, images):
    router.include_router(_module.router)

__all__ = ["router"]
