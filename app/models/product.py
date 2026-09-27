"""Products, their attribute values, variants (SKUs), and images.

Ownership is ``Product -> Shop``. ``created_by_user_id`` and ``updated_by_user_id``
record who acted, for audit; they are not who owns the product.

Several rules here are enforced by the *database*, not only by the service, because
they are relationships the service could get wrong:

* ``product_variants.shop_id`` is a denormalised copy of ``products.shop_id`` (it is
  what lets ``sku_code`` be unique per shop with one index). A composite foreign key
  ``(product_id, shop_id) -> products (id, shop_id)`` makes a mismatch impossible.
* ``product_images.variant_id`` must belong to the image's own product: composite
  ``(variant_id, product_id) -> product_variants (id, product_id)``. When
  ``variant_id`` is NULL the key is not checked (``MATCH SIMPLE``) and the image is a
  product-level image, which is exactly right.
* An ``option_id`` must belong to the ``attribute_id`` next to it:
  ``(option_id, attribute_id) -> attribute_options (id, attribute_id)``.

Child rows (values, variant options) are kept when a product or variant is soft
deleted; see the plan's "Delete semantics".
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.catalog import (
    OPTION_KEY_MAX,
    PRODUCT_DESCRIPTION_MAX,
    PRODUCT_NAME_MAX,
    SKU_CODE_MAX,
    VALUE_TEXT_MAX,
    ProductStatus,
    VariantStatus,
)
from app.constants.identity import MEDIA_KEY_MAX
from app.infrastructure.db.base import Base
from app.infrastructure.db.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

PRODUCT_STATUS_VALUES = ", ".join(f"'{member.value}'" for member in ProductStatus)
VARIANT_STATUS_VALUES = ", ".join(f"'{member.value}'" for member in VariantStatus)


class Product(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A listing owned by one shop.

    ``UNIQUE (id, shop_id)`` exists to be the target of the variants' composite key.
    ``category_id`` is immutable after creation, so attribute values can never end up
    under a category they were not validated against.
    """

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            f"char_length(btrim(name)) between 2 and {PRODUCT_NAME_MAX}",
            name="products_name_ck",
        ),
        CheckConstraint(
            "description is null or "
            f"char_length(description) <= {PRODUCT_DESCRIPTION_MAX}",
            name="products_description_ck",
        ),
        CheckConstraint(
            f"status IN ({PRODUCT_STATUS_VALUES})", name="products_status_ck"
        ),
        UniqueConstraint("id", "shop_id", name="products_id_shop_uniq"),
        Index("products_shop_status_idx", "shop_id", "status"),
        Index("products_category_idx", "category_id"),
        Index("products_brand_idx", "brand_id"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(PRODUCT_NAME_MAX), nullable=False)
    description: Mapped[str | None] = mapped_column(
        String(PRODUCT_DESCRIPTION_MAX), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'draft'")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ProductAttributeValue(Base):
    """One attribute's value on one product (a controlled EAV row).

    Exactly one of ``option_id`` / ``value_text`` / ``value_number`` is set, matching
    the attribute's ``data_type``. A *variation* attribute never appears here: its
    values live on the variants.
    """

    __tablename__ = "product_attribute_values"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(option_id, value_text, value_number) = 1",
            name="pav_exactly_one_value",
        ),
        CheckConstraint(
            f"value_text is null or char_length(value_text) <= {VALUE_TEXT_MAX}",
            name="pav_text_len",
        ),
        ForeignKeyConstraint(
            ["option_id", "attribute_id"],
            ["attribute_options.id", "attribute_options.attribute_id"],
            ondelete="RESTRICT",
            name="pav_option_attribute_fk",
        ),
        Index("pav_attribute_idx", "attribute_id"),
        Index("pav_option_idx", "option_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attributes.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    value_text: Mapped[str | None] = mapped_column(
        String(VALUE_TEXT_MAX), nullable=True
    )
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)


class ProductVariant(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A sellable SKU of a product.

    ``option_key`` is a canonical text form of the variant's option combination (see
    ``utils.catalog.option_key``). A partial unique index over it is what makes two
    concurrent requests unable to create the same combination: the database, not a
    check-then-insert in the service, is the arbiter. The variant's options are
    immutable, so the key never goes stale.

    ``stock`` lives here for now, as the plan records: there is no warehouse yet, and
    the split into ``inventories`` is a later migration.
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint(
            f"char_length(btrim(sku_code)) between 1 and {SKU_CODE_MAX}",
            name="variants_sku_ck",
        ),
        CheckConstraint("price >= 0", name="variants_price_ck"),
        CheckConstraint("stock >= 0", name="variants_stock_ck"),
        CheckConstraint(
            f"status IN ({VARIANT_STATUS_VALUES})", name="variants_status_ck"
        ),
        ForeignKeyConstraint(
            ["product_id", "shop_id"],
            ["products.id", "products.shop_id"],
            ondelete="CASCADE",
            name="variants_product_shop_fk",
        ),
        UniqueConstraint("id", "product_id", name="variants_id_product_uniq"),
        Index(
            "variants_shop_sku_live",
            "shop_id",
            "sku_code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "variants_product_combo_live",
            "product_id",
            "option_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("variants_product_idx", "product_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sku_code: Mapped[str] = mapped_column(String(SKU_CODE_MAX), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stock: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'")
    )
    option_key: Mapped[str] = mapped_column(String(OPTION_KEY_MAX), nullable=False)


class ProductVariantOption(Base):
    """One (attribute, option) that defines a variant, e.g. Color -> Black."""

    __tablename__ = "product_variant_options"
    __table_args__ = (
        ForeignKeyConstraint(
            ["option_id", "attribute_id"],
            ["attribute_options.id", "attribute_options.attribute_id"],
            ondelete="RESTRICT",
            name="pvo_option_attribute_fk",
        ),
        Index("pvo_attribute_idx", "attribute_id"),
        Index("pvo_option_idx", "option_id"),
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attributes.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    option_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class ProductImage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A stored image of a product, or of one of its variants.

    Hard deleted along with its variant or product; the object in storage is removed
    after the transaction commits, best effort.
    """

    __tablename__ = "product_images"
    __table_args__ = (
        CheckConstraint("position >= 0", name="product_images_position_ck"),
        CheckConstraint(
            f"char_length(key) between 1 and {MEDIA_KEY_MAX}",
            name="product_images_key_ck",
        ),
        ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            ondelete="RESTRICT",
            name="product_images_variant_product_fk",
        ),
        Index("product_images_product_idx", "product_id"),
        Index("product_images_variant_idx", "variant_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    key: Mapped[str] = mapped_column(String(MEDIA_KEY_MAX), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
