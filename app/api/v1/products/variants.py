"""A product's variants (SKUs)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.v1.media import get_media_service
from app.api.v1.products.common import Reader, Session, Writer, shop_of, variant_data
from app.schemas.common import BaseResponse
from app.schemas.product import VariantCreateRequest, VariantData, VariantUpdateRequest
from app.services.media_service import MediaService
from app.services.variant_service import OptionInput, VariantService

router = APIRouter(prefix="/api/v1/products/{product_id}/variants", tags=["variants"])


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=BaseResponse[VariantData]
)
async def create_variant(
    request: Request,
    product_id: uuid.UUID,
    payload: VariantCreateRequest,
    principal: Writer,
    session: Session,
) -> BaseResponse[VariantData]:
    detail = await VariantService(session).create_variant(
        shop_id=shop_of(principal),
        product_id=product_id,
        sku_code=payload.sku_code,
        price=payload.price,
        stock=payload.stock,
        status=payload.status,
        options=[
            OptionInput(option.attribute_id, option.option_id)
            for option in payload.options
        ],
    )
    return BaseResponse[VariantData](
        status_code=status.HTTP_201_CREATED, data=variant_data(detail, request)
    )


@router.get("", response_model=BaseResponse[list[VariantData]])
async def list_variants(
    request: Request, product_id: uuid.UUID, principal: Reader, session: Session
) -> BaseResponse[list[VariantData]]:
    details = await VariantService(session).list_variants(
        shop_id=shop_of(principal), product_id=product_id
    )
    return BaseResponse[list[VariantData]](
        status_code=status.HTTP_200_OK,
        data=[variant_data(detail, request) for detail in details],
    )


@router.get("/{variant_id}", response_model=BaseResponse[VariantData])
async def get_variant(
    request: Request,
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    principal: Reader,
    session: Session,
) -> BaseResponse[VariantData]:
    detail = await VariantService(session).get_variant(
        shop_id=shop_of(principal), product_id=product_id, variant_id=variant_id
    )
    return BaseResponse[VariantData](
        status_code=status.HTTP_200_OK, data=variant_data(detail, request)
    )


@router.patch("/{variant_id}", response_model=BaseResponse[VariantData])
async def update_variant(
    request: Request,
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: VariantUpdateRequest,
    principal: Writer,
    session: Session,
) -> BaseResponse[VariantData]:
    changes: dict[str, object] = {
        field: getattr(payload, field)
        for field in ("sku_code", "price", "stock", "status")
        if getattr(payload, field) is not None
    }
    detail = await VariantService(session).update_variant(
        shop_id=shop_of(principal),
        product_id=product_id,
        variant_id=variant_id,
        changes=changes,
    )
    return BaseResponse[VariantData](
        status_code=status.HTTP_200_OK, data=variant_data(detail, request)
    )


@router.delete("/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    principal: Writer,
    session: Session,
    media: Annotated[MediaService, Depends(get_media_service)],
) -> None:
    await VariantService(session, media).delete_variant(
        shop_id=shop_of(principal), product_id=product_id, variant_id=variant_id
    )
