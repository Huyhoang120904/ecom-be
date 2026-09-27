"""Use cases for a shop's products: create, edit, list, delete, publish.

Every method takes the caller's ``shop_id`` and looks the product up *through* it, so a
product of another shop is simply not found. Every write locks the product row first,
which serialises it against that product's other writes.

A status change goes through ``_transition`` and nothing else. ``PATCH`` cannot carry a
status, so there is exactly one path into ``active`` and it runs the invariants.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.catalog import AttributeDataType, ProductStatus
from app.errors.catalog import (
    AttributeIsVariation,
    AttributeNotInCategory,
    BrandNotFound,
    CategoryNotFound,
    CategoryNotLeaf,
    DuplicateAttributeValue,
    InvalidAttributeValue,
    InvalidStatusTransition,
    ProductNotFound,
)
from app.models.product import Product
from app.repositories import (
    attribute_option_repository,
    brand_repository,
    category_attribute_repository,
    category_repository,
    product_attribute_value_repository,
    product_image_repository,
    product_repository,
    variant_repository,
)
from app.services.media_service import MediaService
from app.services.product_rules import enforce_product_invariants
from app.services.product_view import ProductDetail, load_detail
from app.utils.catalog import AttributeValueInput, check_value_matches_type

logger = logging.getLogger(__name__)

# The only status moves that exist. Anything else, ``active -> draft`` included, is
# refused.
ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (ProductStatus.DRAFT, ProductStatus.ACTIVE),
        (ProductStatus.INACTIVE, ProductStatus.ACTIVE),
        (ProductStatus.ACTIVE, ProductStatus.INACTIVE),
    }
)

Row = tuple[uuid.UUID, uuid.UUID | None, str | None, Decimal | None]


class ProductService:
    def __init__(
        self, session: AsyncSession, media: MediaService | None = None
    ) -> None:
        self._session = session
        self._media = media

    # -- reads -------------------------------------------------------------------

    async def _get(
        self, shop_id: uuid.UUID, product_id: uuid.UUID, *, lock: bool = False
    ) -> Product:
        product = await product_repository.get_product(
            self._session, shop_id, product_id, lock=lock
        )
        if product is None:
            raise ProductNotFound
        return product

    async def get_detail(
        self, *, shop_id: uuid.UUID, product_id: uuid.UUID
    ) -> ProductDetail:
        return await load_detail(self._session, await self._get(shop_id, product_id))

    async def list_products(
        self,
        *,
        shop_id: uuid.UUID,
        status: ProductStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Product], int]:
        return await product_repository.list_products(
            self._session,
            shop_id,
            status=status.value if status is not None else None,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    # -- writes ------------------------------------------------------------------

    async def create_product(
        self,
        *,
        shop_id: uuid.UUID,
        user_id: uuid.UUID,
        category_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        name: str,
        description: str | None,
        attributes: list[AttributeValueInput],
    ) -> ProductDetail:
        """Create a ``draft``. A ``FOR SHARE`` lock on the category keeps it a leaf.

        A category that gains a child takes ``FOR UPDATE`` on the same row, so the two
        serialise: the category cannot end up with both a child and a product.
        """

        category = await category_repository.get_category(
            self._session, category_id, lock="share"
        )
        if category is None:
            raise CategoryNotFound
        if await category_repository.has_children(self._session, category_id):
            raise CategoryNotLeaf
        await self._require_brand(brand_id)

        rows = await self._validated_values(category_id, attributes)
        async with self._session.begin_nested():
            product = await product_repository.create_product(
                self._session,
                shop_id=shop_id,
                category_id=category_id,
                brand_id=brand_id,
                name=name,
                description=description,
                user_id=user_id,
            )
            await product_attribute_value_repository.replace_values(
                self._session, product.id, rows
            )
        await self._session.commit()
        return await load_detail(self._session, product)

    async def update_product(
        self,
        *,
        shop_id: uuid.UUID,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        changes: dict[str, object],
        attributes: list[AttributeValueInput] | None,
    ) -> ProductDetail:
        """Edit fields and/or replace the whole set of attribute values.

        ``attributes`` of ``None`` keeps the values; a list (even empty) replaces them.
        On an active product the result must still satisfy the published invariants.
        """

        product = await self._get(shop_id, product_id, lock=True)
        brand = changes.get("brand_id")
        if brand is not None:
            assert isinstance(brand, uuid.UUID)
            await self._require_brand(brand)
        rows = (
            await self._validated_values(product.category_id, attributes)
            if attributes is not None
            else None
        )

        async with self._session.begin_nested():
            await product_repository.update_product(
                self._session, product, changes, user_id=user_id
            )
            if rows is not None:
                await product_attribute_value_repository.replace_values(
                    self._session, product.id, rows
                )
            if product.status == ProductStatus.ACTIVE:
                await enforce_product_invariants(self._session, product)
        await self._session.commit()
        return await load_detail(self._session, product)

    async def delete_product(
        self, *, shop_id: uuid.UUID, user_id: uuid.UUID, product_id: uuid.UUID
    ) -> None:
        """Soft delete the product and its variants; hard delete its images.

        Attribute values and variant options are kept (see the plan's delete
        semantics). Image objects are removed from storage after the commit, best
        effort: an orphaned file is tolerated, a row pointing at a missing file is not.
        """

        product = await self._get(shop_id, product_id, lock=True)
        when = product_repository.now()
        await product_repository.soft_delete_product(
            self._session, product, user_id=user_id, when=when
        )
        await variant_repository.soft_delete_variants_of_product(
            self._session, product.id, when
        )
        keys = await product_image_repository.delete_for_product(
            self._session, product.id
        )
        await self._session.commit()
        await self._remove_objects(keys)

    async def publish(
        self, *, shop_id: uuid.UUID, user_id: uuid.UUID, product_id: uuid.UUID
    ) -> ProductDetail:
        return await self._transition(
            shop_id, user_id, product_id, ProductStatus.ACTIVE
        )

    async def unpublish(
        self, *, shop_id: uuid.UUID, user_id: uuid.UUID, product_id: uuid.UUID
    ) -> ProductDetail:
        return await self._transition(
            shop_id, user_id, product_id, ProductStatus.INACTIVE
        )

    async def _transition(
        self,
        shop_id: uuid.UUID,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        target: ProductStatus,
    ) -> ProductDetail:
        """The single function that changes a product's status."""

        product = await self._get(shop_id, product_id, lock=True)
        if (product.status, target) not in ALLOWED_TRANSITIONS:
            raise InvalidStatusTransition
        if target == ProductStatus.ACTIVE:
            await enforce_product_invariants(self._session, product)
        await product_repository.set_status(
            self._session, product, target.value, user_id=user_id
        )
        await self._session.commit()
        return await load_detail(self._session, product)

    # -- helpers -----------------------------------------------------------------

    async def _require_brand(self, brand_id: uuid.UUID | None) -> None:
        if brand_id is None:
            return
        if await brand_repository.get_brand(self._session, brand_id) is None:
            raise BrandNotFound

    async def _validated_values(
        self, category_id: uuid.UUID, inputs: list[AttributeValueInput]
    ) -> list[Row]:
        """Check each value against the category's configuration and its own type."""

        seen: set[uuid.UUID] = set()
        for value in inputs:
            if value.attribute_id in seen:
                raise DuplicateAttributeValue
            seen.add(value.attribute_id)
        if not inputs:
            return []

        rows_of_category = await category_attribute_repository.list_for_category(
            self._session, category_id
        )
        configuration = {
            attribute.id: (config, attribute) for config, attribute in rows_of_category
        }
        rows: list[Row] = []
        for value in inputs:
            entry = configuration.get(value.attribute_id)
            if entry is None:
                raise AttributeNotInCategory
            config, attribute = entry
            if config.is_variation:
                raise AttributeIsVariation
            valid_options = (
                await attribute_option_repository.option_ids_of(
                    self._session, attribute.id
                )
                if attribute.data_type == AttributeDataType.SELECT
                else set()
            )
            reason = check_value_matches_type(
                attribute.data_type, value, valid_option_ids=valid_options
            )
            if reason is not None:
                logger.info(
                    "Rejected attribute value for %s: %s", attribute.key, reason
                )
                raise InvalidAttributeValue
            rows.append(
                (attribute.id, value.option_id, value.value_text, value.value_number)
            )
        return rows

    async def _remove_objects(self, keys: list[str]) -> None:
        if self._media is None:
            return
        for key in keys:
            try:
                await self._media.delete(key)
            except Exception:  # noqa: BLE001 - an orphaned file must not fail a delete
                logger.warning("Could not remove stored object %s", key)
