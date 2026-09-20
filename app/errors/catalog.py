"""Catalog and product domain errors.

Same contract as ``errors/identity.py``: each class carries its own status and stable
``code``, and ``message`` is a fixed safe string. ``ProductInvariantViolated`` is the
one class that also carries ``details``, built from attribute ids and names the
service resolved from the database, never from request text.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from app.core.errors import AppError

# --- brands ------------------------------------------------------------------


class BrandNotFound(AppError):
    code = "brand_not_found"
    status_code = 404
    message = "Brand not found"


class BrandExists(AppError):
    code = "brand_exists"
    status_code = 409
    message = "A brand with that name already exists"


class BrandInUse(AppError):
    code = "brand_in_use"
    status_code = 409
    message = "This brand is used by products and cannot be deleted"


# --- categories --------------------------------------------------------------


class CategoryNotFound(AppError):
    code = "category_not_found"
    status_code = 404
    message = "Category not found"


class CategoryCycle(AppError):
    code = "category_cycle"
    status_code = 422
    message = "A category cannot be moved under itself or one of its descendants"


class CategoryTooDeep(AppError):
    code = "category_too_deep"
    status_code = 422
    message = "The category tree is too deep"


class CategoryHasChildren(AppError):
    code = "category_has_children"
    status_code = 409
    message = "This category still has sub-categories"


class CategoryHasProducts(AppError):
    code = "category_has_products"
    status_code = 409
    message = "This category has products"


class CategoryNotLeaf(AppError):
    code = "category_not_leaf"
    status_code = 422
    message = "A product must be placed in a category with no sub-categories"


# --- attributes and options --------------------------------------------------


class AttributeNotFound(AppError):
    code = "attribute_not_found"
    status_code = 404
    message = "Attribute not found"


class AttributeExists(AppError):
    code = "attribute_exists"
    status_code = 409
    message = "An attribute with that key already exists"


class AttributeAttached(AppError):
    code = "attribute_attached"
    status_code = 409
    message = "This attribute is still attached to a category"


class AttributeInUse(AppError):
    code = "attribute_in_use"
    status_code = 409
    message = "This attribute is used by products and cannot be deleted"


class OptionNotFound(AppError):
    code = "option_not_found"
    status_code = 404
    message = "Option not found"


class OptionExists(AppError):
    code = "option_exists"
    status_code = 409
    message = "That attribute already has an option with this value"


class OptionInUse(AppError):
    code = "option_in_use"
    status_code = 409
    message = "This option is used by products and cannot be deleted"


class OptionsRequireSelect(AppError):
    code = "options_require_select"
    status_code = 422
    message = "Only a SELECT attribute has options"


class CategoryAttributeNotFound(AppError):
    code = "category_attribute_not_found"
    status_code = 404
    message = "That attribute is not attached to this category"


class VariationRequiresSelect(AppError):
    code = "variation_requires_select"
    status_code = 422
    message = "Only a SELECT attribute can be used to make variants"


class VariationFlagLocked(AppError):
    code = "variation_flag_locked"
    status_code = 409
    message = "Products already use this attribute in this category"


class AttributeDetachLocked(AppError):
    code = "attribute_detach_locked"
    status_code = 409
    message = "Products already use this attribute in this category"


# --- products ----------------------------------------------------------------


class ProductNotFound(AppError):
    code = "product_not_found"
    status_code = 404
    message = "Product not found"


class InvalidStatusTransition(AppError):
    code = "invalid_status_transition"
    status_code = 409
    message = "That status change is not allowed"


class InvalidAttributeValue(AppError):
    code = "invalid_attribute_value"
    status_code = 422
    message = "An attribute value is invalid for its attribute"


class AttributeNotInCategory(AppError):
    code = "attribute_not_in_category"
    status_code = 422
    message = "An attribute is not configured for this product's category"


class AttributeIsVariation(AppError):
    code = "attribute_is_variation"
    status_code = 422
    message = "A variation attribute is set on variants, not on the product"


class DuplicateAttributeValue(AppError):
    code = "duplicate_attribute_value"
    status_code = 422
    message = "An attribute was given more than once"


class MissingItem(TypedDict):
    """One thing a product still needs before it can be active."""

    attribute_id: str
    name: str
    where: str


class ProductInvariantViolated(AppError):
    """The product would not satisfy the rules an active product must satisfy.

    ``details`` names what is missing (attribute id, its name, and whether it is
    missing from the product or from its variants) so a client can prompt the seller.
    """

    code = "product_invariant_violated"
    status_code = 422
    message = "The product does not meet the requirements to be active"

    def __init__(self, missing: Sequence[MissingItem], *, reasons: Sequence[str] = ()):
        super().__init__()
        self.details = {"missing": list(missing), "reasons": list(reasons)}


# --- variants ----------------------------------------------------------------


class VariantNotFound(AppError):
    code = "variant_not_found"
    status_code = 404
    message = "Variant not found"


class SkuExists(AppError):
    code = "sku_exists"
    status_code = 409
    message = "That SKU code is already used in this shop"


class VariantCombinationExists(AppError):
    code = "variant_combination_exists"
    status_code = 409
    message = "A variant with this combination of options already exists"


class VariantOptionInvalid(AppError):
    code = "variant_option_invalid"
    status_code = 422
    message = "A variant option is not valid for this product"


class VariationSetInconsistent(AppError):
    code = "variation_set_inconsistent"
    status_code = 422
    message = "Every variant of a product must use the same variation attributes"


class LastActiveVariant(AppError):
    code = "last_active_variant"
    status_code = 409
    message = "An active product needs at least one active variant"


# --- images ------------------------------------------------------------------


class ProductImageNotFound(AppError):
    code = "product_image_not_found"
    status_code = 404
    message = "Image not found"


class ImageLimitReached(AppError):
    code = "image_limit_reached"
    status_code = 409
    message = "The image limit for this product or variant has been reached"


class InvalidImagePosition(AppError):
    code = "invalid_image_position"
    status_code = 422
    message = "The image position is out of range"


class ImageVariantInvalid(AppError):
    code = "image_variant_invalid"
    status_code = 422
    message = "That variant does not belong to this product"
