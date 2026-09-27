"""Closed vocabularies of the catalog and product domains.

Each is a ``StrEnum`` so the value is the wire and the column value, and the same
tuple feeds the ``CHECK`` constraint so the model and the database cannot disagree.
"""

from enum import StrEnum


class AttributeDataType(StrEnum):
    """How an attribute's value is entered and stored."""

    TEXT = "TEXT"
    NUMBER = "NUMBER"
    SELECT = "SELECT"


class ProductStatus(StrEnum):
    """A product's lifecycle. Only ``publish``/``unpublish`` move it after creation."""

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"


class VariantStatus(StrEnum):
    """Whether a variant can currently be sold."""

    ACTIVE = "active"
    INACTIVE = "inactive"
