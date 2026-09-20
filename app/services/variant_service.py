"""Use cases for a product's variants (SKUs).

Every write locks the product row ``FOR UPDATE`` first. The rules that look across
variants (all use the same variation attributes; an active product keeps one active
variant) are read-then-decide, and the lock is what stops two requests deciding on the
same stale picture. The combination and SKU uniqueness do not rely on that lock: the
partial unique indexes are the arbiters and a violation is mapped to ``409``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.catalog import AttributeDataType, ProductStatus, VariantStatus
from app.errors.catalog import (
    LastActiveVariant,
    ProductNotFound,
    SkuExists,
    VariantCombinationExists,
    VariantNotFound,
    VariantOptionInvalid,
    VariationSetInconsistent,
)
from app.models.product import Product, ProductVariant
from app.repositories import (
    attribute_option_repository,
    category_attribute_repository,
    product_image_repository,
    product_repository,
    variant_option_repository,
    variant_repository,
)
from app.services.media_service import MediaService
from app.services.product_rules import enforce_product_invariants
from app.services.product_view import VariantDetail, load_variant, variant_details
from app.utils.catalog import option_key, variation_sets_consistent

logger = logging.getLogger(__name__)

SKU_INDEX = "variants_shop_sku_live"
COMBINATION_INDEX = "variants_product_combo_live"


@dataclass(frozen=True, slots=True)
class OptionInput:
    attribute_id: uuid.UUID
    option_id: uuid.UUID


class VariantService:
    def __init__(
        self, session: AsyncSession, media: MediaService | None = None
    ) -> None:
        self._session = session
        self._media = media

    # -- reads -------------------------------------------------------------------

    async def _product(
        self, shop_id: uuid.UUID, product_id: uuid.UUID, *, lock: bool = False
    ) -> Product:
        product = await product_repository.get_product(
            self._session, shop_id, product_id, lock=lock
        )
        if product is None:
            raise ProductNotFound
        return product

    async def list_variants(
        self, *, shop_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[VariantDetail]:
        product = await self._product(shop_id, product_id)
        variants = await variant_repository.list_variants(self._session, product.id)
        images = await product_image_repository.list_for_product(
            self._session, product.id
        )
        return await variant_details(self._session, variants, images)

    async def get_variant(
        self, *, shop_id: uuid.UUID, product_id: uuid.UUID, variant_id: uuid.UUID
    ) -> VariantDetail:
        product = await self._product(shop_id, product_id)
        variant = await self._variant(product.id, variant_id)
        return await load_variant(self._session, product.id, variant)

    async def _variant(
        self, product_id: uuid.UUID, variant_id: uuid.UUID
    ) -> ProductVariant:
        variant = await variant_repository.get_variant(
            self._session, product_id, variant_id
        )
        if variant is None:
            raise VariantNotFound
        return variant

    # -- writes ------------------------------------------------------------------

    async def create_variant(
        self,
        *,
        shop_id: uuid.UUID,
        product_id: uuid.UUID,
        sku_code: str,
        price: int,
        stock: int,
        status: VariantStatus,
        options: list[OptionInput],
    ) -> VariantDetail:
        product = await self._product(shop_id, product_id, lock=True)
        pairs = await self._validated_options(product, options)
        await self._require_consistent_set(product, frozenset(a for a, _ in pairs))

        try:
            async with self._session.begin_nested():
                variant = await variant_repository.create_variant(
                    self._session,
                    product_id=product.id,
                    shop_id=product.shop_id,
                    sku_code=sku_code,
                    price=price,
                    stock=stock,
                    status=status.value,
                    option_key=option_key(pairs),
                )
                await variant_option_repository.create_options(
                    self._session, variant.id, pairs
                )
                if product.status == ProductStatus.ACTIVE:
                    await enforce_product_invariants(self._session, product)
        except IntegrityError as error:
            raise _uniqueness_error(error) from error
        await self._session.commit()
        return await load_variant(self._session, product.id, variant)

    async def update_variant(
        self,
        *,
        shop_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID,
        changes: dict[str, object],
    ) -> VariantDetail:
        product = await self._product(shop_id, product_id, lock=True)
        variant = await self._variant(product.id, variant_id)

        if changes.get("status") == VariantStatus.INACTIVE:
            await self._require_another_active(product, variant)
        if "status" in changes:
            changes = {**changes, "status": VariantStatus(str(changes["status"])).value}

        try:
            async with self._session.begin_nested():
                await variant_repository.update_variant(self._session, variant, changes)
                if product.status == ProductStatus.ACTIVE:
                    await enforce_product_invariants(self._session, product)
        except IntegrityError as error:
            raise _uniqueness_error(error) from error
        await self._session.commit()
        return await load_variant(self._session, product.id, variant)

    async def delete_variant(
        self, *, shop_id: uuid.UUID, product_id: uuid.UUID, variant_id: uuid.UUID
    ) -> None:
        """Soft delete a variant, keeping its options; hard delete its images."""

        product = await self._product(shop_id, product_id, lock=True)
        variant = await self._variant(product.id, variant_id)
        await self._require_another_active(product, variant)

        await variant_repository.soft_delete_variant(
            self._session, variant, product_repository.now()
        )
        keys = await product_image_repository.delete_for_variant(
            self._session, product.id, variant.id
        )
        await self._session.commit()
        await self._remove_objects(keys)

    # -- rules -------------------------------------------------------------------

    async def _validated_options(
        self, product: Product, options: list[OptionInput]
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Each option must be a variation of the category, with one of its options."""

        rows_of_category = await category_attribute_repository.list_for_category(
            self._session, product.category_id
        )
        configuration = {
            attribute.id: (config, attribute) for config, attribute in rows_of_category
        }
        seen: set[uuid.UUID] = set()
        pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
        for option in options:
            entry = configuration.get(option.attribute_id)
            if entry is None or option.attribute_id in seen:
                raise VariantOptionInvalid
            config, attribute = entry
            if (
                not config.is_variation
                or attribute.data_type != AttributeDataType.SELECT
            ):
                raise VariantOptionInvalid
            valid = await attribute_option_repository.option_ids_of(
                self._session, attribute.id
            )
            if option.option_id not in valid:
                raise VariantOptionInvalid
            seen.add(option.attribute_id)
            pairs.append((option.attribute_id, option.option_id))
        return pairs

    async def _require_consistent_set(
        self, product: Product, candidate: frozenset[uuid.UUID]
    ) -> None:
        existing = await variant_repository.list_variants(self._session, product.id)
        by_variant = await variant_option_repository.attribute_ids_by_variant(
            self._session, [variant.id for variant in existing]
        )
        shapes = [by_variant.get(variant.id, frozenset()) for variant in existing]
        if not variation_sets_consistent(shapes, candidate):
            raise VariationSetInconsistent

    async def _require_another_active(
        self, product: Product, variant: ProductVariant
    ) -> None:
        """An active product keeps at least one active variant."""

        if (
            product.status != ProductStatus.ACTIVE
            or variant.status != VariantStatus.ACTIVE
        ):
            return
        others = [
            other
            for other in await variant_repository.list_variants(
                self._session, product.id
            )
            if other.id != variant.id and other.status == VariantStatus.ACTIVE
        ]
        if not others:
            raise LastActiveVariant

    async def _remove_objects(self, keys: list[str]) -> None:
        if self._media is None:
            return
        for key in keys:
            try:
                await self._media.delete(key)
            except Exception:  # noqa: BLE001 - an orphaned file must not fail a delete
                logger.warning("Could not remove stored object %s", key)


def _uniqueness_error(error: IntegrityError) -> Exception:
    """Map the unique index a violation named to its specific ``409``."""

    text = str(error)
    if SKU_INDEX in text:
        return SkuExists()
    if COMBINATION_INDEX in text:
        return VariantCombinationExists()
    return error
