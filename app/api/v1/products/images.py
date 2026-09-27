"""A product's images, and its variants' images."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from app.api.deps import get_optional_redis_client
from app.api.v1.identity.common import _client_key
from app.api.v1.media import get_media_service
from app.api.v1.products.common import Session, Writer, image_data, shop_of
from app.schemas.common import BaseResponse
from app.schemas.product import ImageData, ImagePositionRequest
from app.services.media_service import MediaService
from app.services.product_image_service import ProductImageService
from app.services.rate_limit_service import (
    UPLOAD_LIMIT,
    UPLOAD_WINDOW_SECONDS,
    RateLimitStore,
    enforce_rate_limit,
)

router = APIRouter(prefix="/api/v1/products/{product_id}/images", tags=["images"])


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=BaseResponse[ImageData]
)
async def upload_image(
    request: Request,
    product_id: uuid.UUID,
    principal: Writer,
    session: Session,
    media: Annotated[MediaService, Depends(get_media_service)],
    file: Annotated[UploadFile, File()],
    variant_id: Annotated[uuid.UUID | None, Form()] = None,
    redis: Annotated[RateLimitStore | None, Depends(get_optional_redis_client)] = None,
) -> BaseResponse[ImageData]:
    """Add an image to the product, or to a variant when ``variant_id`` is set."""

    await enforce_rate_limit(
        redis,
        key=_client_key(request, "upload"),
        limit=UPLOAD_LIMIT,
        window_seconds=UPLOAD_WINDOW_SECONDS,
    )
    image = await ProductImageService(session, media).upload(
        shop_id=shop_of(principal),
        product_id=product_id,
        variant_id=variant_id,
        image_bytes=await file.read(),
        declared_content_type=file.content_type or "application/octet-stream",
    )
    return BaseResponse[ImageData](
        status_code=status.HTTP_201_CREATED, data=image_data(image, request)
    )


@router.patch("/{image_id}", response_model=BaseResponse[list[ImageData]])
async def move_image(
    request: Request,
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    payload: ImagePositionRequest,
    principal: Writer,
    session: Session,
    media: Annotated[MediaService, Depends(get_media_service)],
) -> BaseResponse[list[ImageData]]:
    """Move an image to ``position`` in its scope; the scope comes back in order."""

    scope = await ProductImageService(session, media).move(
        shop_id=shop_of(principal),
        product_id=product_id,
        image_id=image_id,
        position=payload.position,
    )
    return BaseResponse[list[ImageData]](
        status_code=status.HTTP_200_OK,
        data=[image_data(image, request) for image in scope],
    )


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    principal: Writer,
    session: Session,
    media: Annotated[MediaService, Depends(get_media_service)],
) -> None:
    await ProductImageService(session, media).delete(
        shop_id=shop_of(principal), product_id=product_id, image_id=image_id
    )
