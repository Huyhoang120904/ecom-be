"""Brands: a read list for any caller, writes for a catalog manager."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.v1.catalog.common import Caller, CatalogAdmin, Session, brand_data
from app.schemas.catalog import BrandCreateRequest, BrandData, BrandUpdateRequest
from app.schemas.common import BaseResponse
from app.services.brand_service import BrandService

read_router = APIRouter(prefix="/api/v1/catalog/brands", tags=["catalog"])
admin_router = APIRouter(prefix="/api/v1/admin/catalog/brands", tags=["catalog-admin"])


@read_router.get("", response_model=BaseResponse[list[BrandData]])
async def list_brands(_: Caller, session: Session) -> BaseResponse[list[BrandData]]:
    brands = await BrandService(session).list_brands()
    return BaseResponse[list[BrandData]](
        status_code=status.HTTP_200_OK, data=[brand_data(brand) for brand in brands]
    )


@admin_router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=BaseResponse[BrandData]
)
async def create_brand(
    payload: BrandCreateRequest, _: CatalogAdmin, session: Session
) -> BaseResponse[BrandData]:
    brand = await BrandService(session).create_brand(name=payload.name)
    return BaseResponse[BrandData](
        status_code=status.HTTP_201_CREATED, data=brand_data(brand)
    )


@admin_router.patch("/{brand_id}", response_model=BaseResponse[BrandData])
async def rename_brand(
    brand_id: uuid.UUID,
    payload: BrandUpdateRequest,
    _: CatalogAdmin,
    session: Session,
) -> BaseResponse[BrandData]:
    brand = await BrandService(session).rename_brand(
        brand_id=brand_id, name=payload.name
    )
    return BaseResponse[BrandData](
        status_code=status.HTTP_200_OK, data=brand_data(brand)
    )


@admin_router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(brand_id: uuid.UUID, _: CatalogAdmin, session: Session) -> None:
    await BrandService(session).delete_brand(brand_id)
