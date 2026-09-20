"""Catalog request and response schemas, one module per flow.

The router layer is split the same way (``app/api/v1/catalog/``). This package
re-exports every model; ``__all__`` is spelled out because ``no_implicit_reexport``
makes an unlisted re-export a type error. Every string is bounded and every ``2xx``
body is a ``BaseResponse``: the same two contract gates as identity.
"""

from app.schemas.catalog.attribute import (
    AttributeCreateRequest,
    AttributeData,
    AttributeUpdateRequest,
    OptionCreateRequest,
    OptionData,
    OptionUpdateRequest,
)
from app.schemas.catalog.brand import BrandCreateRequest, BrandData, BrandUpdateRequest
from app.schemas.catalog.category import (
    CategoryCreateRequest,
    CategoryData,
    CategoryTreeNode,
    CategoryUpdateRequest,
)
from app.schemas.catalog.category_attribute import (
    CategoryAttributeData,
    CategoryAttributeRequest,
)

__all__ = [
    "AttributeCreateRequest",
    "AttributeData",
    "AttributeUpdateRequest",
    "BrandCreateRequest",
    "BrandData",
    "BrandUpdateRequest",
    "CategoryAttributeData",
    "CategoryAttributeRequest",
    "CategoryCreateRequest",
    "CategoryData",
    "CategoryTreeNode",
    "CategoryUpdateRequest",
    "OptionCreateRequest",
    "OptionData",
    "OptionUpdateRequest",
]
