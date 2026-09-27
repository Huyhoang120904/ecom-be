"""A shop's products: create, list, read, edit, delete, publish and unpublish."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.v1.media import get_media_service
from app.api.v1.products.common import (
    Reader,
    Session,
    Writer,
    product_data,
    product_summary,
    shop_of,
    user_of,
    value_inputs,
)
from app.constants.catalog import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, ProductStatus
from app.schemas.common import BaseResponse
from app.schemas.product import (
    ProductCreateRequest,
    ProductData,
    ProductPage,
    ProductUpdateRequest,
)
from app.services.media_service import MediaService
from app.services.product_service import ProductService

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=BaseResponse[ProductData]
)
async def create_product(
    request: Request,
    payload: ProductCreateRequest,
    principal: Writer,
    session: Session,
) -> BaseResponse[ProductData]:
    detail = await ProductService(session).create_product(
        shop_id=shop_of(principal),
        user_id=user_of(principal),
        category_id=payload.category_id,
        brand_id=payload.brand_id,
        name=payload.name,
        description=payload.description,
        attributes=value_inputs(payload.attributes),
    )
    return BaseResponse[ProductData](
        status_code=status.HTTP_201_CREATED, data=product_data(detail, request)
    )


@router.get("", response_model=BaseResponse[ProductPage])
async def list_products(
    principal: Reader,
    session: Session,
    product_status: Annotated[ProductStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
) -> BaseResponse[ProductPage]:
    products, total = await ProductService(session).list_products(
        shop_id=shop_of(principal),
        status=product_status,
        page=page,
        page_size=page_size,
    )
    return BaseResponse[ProductPage](
        status_code=status.HTTP_200_OK,
        data=ProductPage(
            items=[product_summary(product) for product in products],
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.get("/{product_id}", response_model=BaseResponse[ProductData])
async def get_product(
    request: Request, product_id: uuid.UUID, principal: Reader, session: Session
) -> BaseResponse[ProductData]:
    detail = await ProductService(session).get_detail(
        shop_id=shop_of(principal), product_id=product_id
    )
    return BaseResponse[ProductData](
        status_code=status.HTTP_200_OK, data=product_data(detail, request)
    )


@router.patch("/{product_id}", response_model=BaseResponse[ProductData])
async def update_product(
    request: Request,
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
    principal: Writer,
    session: Session,
) -> BaseResponse[ProductData]:
    sent = payload.model_fields_set
    changes: dict[str, object] = {
        field: getattr(payload, field)
        for field in ("name", "description", "brand_id")
        if field in sent
    }
    attributes = (
        value_inputs(payload.attributes) if payload.attributes is not None else None
    )
    detail = await ProductService(session).update_product(
        shop_id=shop_of(principal),
        user_id=user_of(principal),
        product_id=product_id,
        changes=changes,
        attributes=attributes,
    )
    return BaseResponse[ProductData](
        status_code=status.HTTP_200_OK, data=product_data(detail, request)
    )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    principal: Writer,
    session: Session,
    media: Annotated[MediaService, Depends(get_media_service)],
) -> None:
    await ProductService(session, media).delete_product(
        shop_id=shop_of(principal), user_id=user_of(principal), product_id=product_id
    )


@router.post("/{product_id}/publish", response_model=BaseResponse[ProductData])
async def publish_product(
    request: Request, product_id: uuid.UUID, principal: Writer, session: Session
) -> BaseResponse[ProductData]:
    detail = await ProductService(session).publish(
        shop_id=shop_of(principal), user_id=user_of(principal), product_id=product_id
    )
    return BaseResponse[ProductData](
        status_code=status.HTTP_200_OK, data=product_data(detail, request)
    )


@router.post("/{product_id}/unpublish", response_model=BaseResponse[ProductData])
async def unpublish_product(
    request: Request, product_id: uuid.UUID, principal: Writer, session: Session
) -> BaseResponse[ProductData]:
    detail = await ProductService(session).unpublish(
        shop_id=shop_of(principal), user_id=user_of(principal), product_id=product_id
    )
    return BaseResponse[ProductData](
        status_code=status.HTTP_200_OK, data=product_data(detail, request)
    )
