"""The shared catalog: brands, categories, attributes, options, and their wiring.

Everything here is marketplace-wide reference data, not shop data: a shop's products
point *at* it. So none of it carries a ``shop_id``, and none of it is soft deleted:
an entry is either referenced (and ``RESTRICT`` foreign keys keep it) or it is gone.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.catalog import (
    ATTRIBUTE_KEY_MAX,
    ATTRIBUTE_NAME_MAX,
    BRAND_NAME_MAX,
    CATALOG_SLUG_MAX,
    CATEGORY_NAME_MAX,
    OPTION_VALUE_MAX,
    AttributeDataType,
)
from app.infrastructure.db.base import Base
from app.infrastructure.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

CATALOG_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
ATTRIBUTE_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"

DATA_TYPE_VALUES = ", ".join(f"'{member.value}'" for member in AttributeDataType)


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A product brand.

    ``name`` is ``citext`` so "Nike" and "nike" are one brand. ``slug`` is derived once
    from the name and never changes on rename, for the same reason a shop's does.
    """

    __tablename__ = "brands"
    __table_args__ = (
        CheckConstraint(
            f"char_length(btrim(name)) between 1 and {BRAND_NAME_MAX}",
            name="brands_name_ck",
        ),
        CheckConstraint(f"slug ~ '{CATALOG_SLUG_PATTERN}'", name="brands_slug_ck"),
        CheckConstraint(
            f"char_length(slug) between 1 and {CATALOG_SLUG_MAX}",
            name="brands_slug_len",
        ),
        UniqueConstraint("name", name="brands_name_uniq"),
        UniqueConstraint("slug", name="brands_slug_uniq"),
    )

    name: Mapped[str] = mapped_column(CITEXT, nullable=False)
    slug: Mapped[str] = mapped_column(String(CATALOG_SLUG_MAX), nullable=False)


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A node in the category tree.

    A product may only sit in a *leaf*; the service and a ``FOR UPDATE`` / ``FOR
    SHARE`` pair on the category row keep "has children" and "has products" from both
    becoming true at once.
    """

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(
            f"char_length(btrim(name)) between 1 and {CATEGORY_NAME_MAX}",
            name="categories_name_ck",
        ),
        CheckConstraint(f"slug ~ '{CATALOG_SLUG_PATTERN}'", name="categories_slug_ck"),
        CheckConstraint(
            f"char_length(slug) between 1 and {CATALOG_SLUG_MAX}",
            name="categories_slug_len",
        ),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="categories_not_own_parent"
        ),
        CheckConstraint("position >= 0", name="categories_position_ck"),
        UniqueConstraint("slug", name="categories_slug_uniq"),
        Index("categories_parent_idx", "parent_id"),
    )

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(CATEGORY_NAME_MAX), nullable=False)
    slug: Mapped[str] = mapped_column(String(CATALOG_SLUG_MAX), nullable=False)
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class Attribute(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A property a product can have, such as Color or RAM.

    ``key`` and ``data_type`` are immutable after creation: changing what an attribute
    *is* under products that already use it has no safe meaning, so a different meaning
    is a different attribute.
    """

    __tablename__ = "attributes"
    __table_args__ = (
        CheckConstraint(f"key ~ '{ATTRIBUTE_KEY_PATTERN}'", name="attributes_key_ck"),
        CheckConstraint(
            f"char_length(key) between 2 and {ATTRIBUTE_KEY_MAX}",
            name="attributes_key_len",
        ),
        CheckConstraint(
            f"char_length(btrim(name)) between 1 and {ATTRIBUTE_NAME_MAX}",
            name="attributes_name_ck",
        ),
        CheckConstraint(
            f"data_type IN ({DATA_TYPE_VALUES})", name="attributes_data_type_ck"
        ),
        UniqueConstraint("key", name="attributes_key_uniq"),
    )

    key: Mapped[str] = mapped_column(String(ATTRIBUTE_KEY_MAX), nullable=False)
    name: Mapped[str] = mapped_column(String(ATTRIBUTE_NAME_MAX), nullable=False)
    data_type: Mapped[str] = mapped_column(String(16), nullable=False)


class AttributeOption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One allowed value of a ``SELECT`` attribute.

    ``UNIQUE (id, attribute_id)`` exists only to be the target of composite foreign
    keys: it is what lets the database prove that an option really belongs to the
    attribute a product value or a variant option claims.
    """

    __tablename__ = "attribute_options"
    __table_args__ = (
        CheckConstraint(
            f"char_length(btrim(value)) between 1 and {OPTION_VALUE_MAX}",
            name="attribute_options_value_ck",
        ),
        CheckConstraint("sort_order >= 0", name="attribute_options_sort_ck"),
        UniqueConstraint("attribute_id", "value", name="attribute_options_value_uniq"),
        UniqueConstraint("id", "attribute_id", name="attribute_options_id_attr_uniq"),
    )

    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attributes.id", ondelete="CASCADE"),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(String(OPTION_VALUE_MAX), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class CategoryAttribute(Base):
    """Which attributes a category asks a product for, and how.

    ``is_variation`` marks an attribute the seller varies to make variants (Color,
    Size). It is what lets the system validate ``product_variant_options`` without
    knowing what a "variation" means.

    A join with a composite primary key and no lifecycle of its own.
    """

    __tablename__ = "category_attributes"
    __table_args__ = (
        CheckConstraint("position >= 0", name="category_attrs_pos_ck"),
        Index("category_attrs_attr_idx", "attribute_id"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attributes.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    filterable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    searchable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_variation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
