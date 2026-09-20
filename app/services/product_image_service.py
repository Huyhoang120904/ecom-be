"""Use cases for product and variant images.

An image belongs to a *scope*: the product itself (``variant_id`` is ``NULL``) or one of
its variants. Each scope has its own limit and its own ``0..n-1`` ordering.

The order of operations on upload is chosen for the failure that matters: the file is
stored first and the row second, so a failure leaves at worst an orphaned file (which
is tolerated) and never a row that points at nothing.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.catalog import PRODUCT_IMAGES_MAX, VARIANT_IMAGES_MAX
from app.errors.catalog import (
    ImageLimitReached,
    ImageVariantInvalid,
    InvalidImagePosition,
    ProductImageNotFound,
    ProductNotFound,
)
from app.models.product import Product, ProductImage
from app.repositories import (
    product_image_repository,
    product_repository,
    variant_repository,
)
from app.services.media_service import MediaService
from app.utils.catalog import reorder

logger = logging.getLogger(__name__)


class ProductImageService:
    def __init__(self, session: AsyncSession, media: MediaService) -> None:
        self._session = session
        self._media = media

    async def _locked_product(
        self, shop_id: uuid.UUID, product_id: uuid.UUID
    ) -> Product:
        product = await product_repository.get_product(
            self._session, shop_id, product_id, lock=True
        )
        if product is None:
            raise ProductNotFound
        return product

    async def upload(
        self,
        *,
        shop_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
        image_bytes: bytes,
        declared_content_type: str,
    ) -> ProductImage:
        product = await self._locked_product(shop_id, product_id)
        if variant_id is not None:
            variant = await variant_repository.get_variant(
                self._session, product.id, variant_id
            )
            if variant is None:
                raise ImageVariantInvalid

        limit = PRODUCT_IMAGES_MAX if variant_id is None else VARIANT_IMAGES_MAX
        existing = await product_image_repository.count_scope(
            self._session, product.id, variant_id
        )
        if existing >= limit:
            raise ImageLimitReached

        image_id = uuid.uuid4()
        key = await self._media.store_product_image(
            image_id=image_id,
            image_bytes=image_bytes,
            declared_content_type=declared_content_type,
        )
        try:
            image = await product_image_repository.create_image(
                self._session,
                image_id=image_id,
                product_id=product.id,
                variant_id=variant_id,
                key=key,
                position=existing,
            )
            await self._session.commit()
        except BaseException:
            await self._forget(key)
            raise
        return image

    async def move(
        self,
        *,
        shop_id: uuid.UUID,
        product_id: uuid.UUID,
        image_id: uuid.UUID,
        position: int,
    ) -> list[ProductImage]:
        """Move an image to ``position`` in its scope; return that scope in order."""

        product = await self._locked_product(shop_id, product_id)
        image = await product_image_repository.get_product_image(
            self._session, product.id, image_id
        )
        if image is None:
            raise ProductImageNotFound
        scope = await product_image_repository.list_scope(
            self._session, product.id, image.variant_id
        )
        by_id = {item.id: item for item in scope}
        try:
            order = reorder([item.id for item in scope], image.id, position)
        except ValueError as error:
            raise InvalidImagePosition from error
        await product_image_repository.set_positions(
            self._session, [by_id[item_id] for item_id in order]
        )
        await self._session.commit()
        return [by_id[item_id] for item_id in order]

    async def delete(
        self, *, shop_id: uuid.UUID, product_id: uuid.UUID, image_id: uuid.UUID
    ) -> None:
        product = await self._locked_product(shop_id, product_id)
        image = await product_image_repository.get_product_image(
            self._session, product.id, image_id
        )
        if image is None:
            raise ProductImageNotFound
        key, variant_id = image.key, image.variant_id
        await product_image_repository.delete_image(self._session, image)
        remaining = await product_image_repository.list_scope(
            self._session, product.id, variant_id
        )
        await product_image_repository.set_positions(self._session, remaining)
        await self._session.commit()
        await self._forget(key)

    async def _forget(self, key: str) -> None:
        try:
            await self._media.delete(key)
        except Exception:  # noqa: BLE001 - an orphaned file must not fail the request
            logger.warning("Could not remove stored object %s", key)
