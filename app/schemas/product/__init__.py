"""Product, variant and image request and response schemas, one module per flow.

Every string is bounded and every ``2xx`` body is a ``BaseResponse``: the same two
contract gates as identity and the catalog. ``__all__`` is spelled out because
``no_implicit_reexport`` makes an unlisted re-export a type error.
"""

from app.schemas.product.image import ImageData, ImagePositionRequest
from app.schemas.product.product import (
    AttributeValueRequest,
    ProductAttributeData,
    ProductCreateRequest,
    ProductData,
    ProductPage,
    ProductSummary,
    ProductUpdateRequest,
)
from app.schemas.product.variant import (
    VariantCreateRequest,
    VariantData,
    VariantOptionData,
    VariantOptionRequest,
    VariantUpdateRequest,
)

__all__ = [
    "AttributeValueRequest",
    "ImageData",
    "ImagePositionRequest",
    "ProductAttributeData",
    "ProductCreateRequest",
    "ProductData",
    "ProductPage",
    "ProductSummary",
    "ProductUpdateRequest",
    "VariantCreateRequest",
    "VariantData",
    "VariantOptionData",
    "VariantOptionRequest",
    "VariantUpdateRequest",
]
