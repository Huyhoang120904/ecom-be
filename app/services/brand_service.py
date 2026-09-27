"""Use cases for brands."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors.catalog import BrandExists, BrandInUse, BrandNotFound
from app.models.catalog import Brand
from app.repositories import brand_repository


class BrandService:
    """The shared brand list. Writes are guarded at the route by ``catalog:manage``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_brands(self) -> list[Brand]:
        return await brand_repository.list_brands(self._session)

    async def get_brand(self, brand_id: uuid.UUID) -> Brand:
        brand = await brand_repository.get_brand(self._session, brand_id)
        if brand is None:
            raise BrandNotFound
        return brand

    async def create_brand(self, *, name: str) -> Brand:
        try:
            # A savepoint, so the losing side of a duplicate name unwinds only this
            # insert and the caller's transaction stays usable.
            async with self._session.begin_nested():
                brand = await brand_repository.create_brand(self._session, name=name)
        except IntegrityError as error:
            raise BrandExists from error
        await self._session.commit()
        return brand

    async def rename_brand(self, *, brand_id: uuid.UUID, name: str) -> Brand:
        brand = await self.get_brand(brand_id)
        try:
            async with self._session.begin_nested():
                await brand_repository.rename_brand(self._session, brand, name)
        except IntegrityError as error:
            raise BrandExists from error
        await self._session.commit()
        return brand

    async def delete_brand(self, brand_id: uuid.UUID) -> None:
        await self.get_brand(brand_id)
        if await brand_repository.brand_has_products(self._session, brand_id):
            raise BrandInUse
        await brand_repository.delete_brand(self._session, brand_id)
        await self._session.commit()
