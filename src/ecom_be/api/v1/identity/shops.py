"""The active shop: profile update, background upload, and deletion."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.api.deps import (
    get_application_db_session,
    get_optional_redis_client,
    require_permissions,
)
from ecom_be.api.principal import Principal
from ecom_be.api.v1.identity.common import _client_key, _shop_data
from ecom_be.api.v1.media import get_media_service
from ecom_be.schemas.identity import DeleteShopRequest, ShopEnvelope, ShopUpdateRequest
from ecom_be.services.identity import (
    UPLOAD_LIMIT,
    UPLOAD_WINDOW_SECONDS,
    IdentityService,
    RateLimitStore,
    enforce_rate_limit,
)
from ecom_be.services.media import MediaService

shops_router = APIRouter(prefix="/api/v1/shops", tags=["shops"])


@shops_router.post("/active/background", response_model=ShopEnvelope)
async def upload_background(
    request: Request,
    principal: Annotated[Principal, Depends(require_permissions("shop:update"))],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    media: Annotated[MediaService, Depends(get_media_service)],
    file: Annotated[UploadFile, File()],
    redis: Annotated[RateLimitStore | None, Depends(get_optional_redis_client)] = None,
) -> ShopEnvelope:
    await enforce_rate_limit(
        redis,
        key=_client_key(request, "upload"),
        limit=UPLOAD_LIMIT,
        window_seconds=UPLOAD_WINDOW_SECONDS,
    )
    payload = await file.read()
    key = await media.store_background(
        shop_id=uuid.UUID(principal.active_shop_id),
        image_bytes=payload,
        declared_content_type=file.content_type or "application/octet-stream",
    )
    shop = await IdentityService(session).set_shop_background(
        shop_id=uuid.UUID(principal.active_shop_id), key=key
    )
    return ShopEnvelope(data=_shop_data(shop, request))


@shops_router.delete("/active/background", status_code=status.HTTP_204_NO_CONTENT)
async def delete_background(
    principal: Annotated[Principal, Depends(require_permissions("shop:update"))],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    media: Annotated[MediaService, Depends(get_media_service)],
) -> None:
    service = IdentityService(session)
    shop = await service.active_shop(uuid.UUID(principal.active_shop_id))
    if shop.background_key:
        await media.delete(shop.background_key)
    await service.set_shop_background(shop_id=shop.id, key=None)


@shops_router.patch("/active", response_model=ShopEnvelope)
async def update_active_shop(
    payload: ShopUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_permissions("shop:update"))],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> ShopEnvelope:
    """Update the active shop's profile. The slug is not part of the contract."""

    service = IdentityService(session)
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    shop = await service.update_active_shop(
        shop_id=uuid.UUID(principal.active_shop_id), changes=changes
    )
    return ShopEnvelope(data=_shop_data(shop, request))


@shops_router.delete("/active", status_code=status.HTTP_204_NO_CONTENT)
async def delete_active_shop(
    payload: DeleteShopRequest,
    principal: Annotated[Principal, Depends(require_permissions("shop:update"))],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> None:
    """Retire the shop. Confirmed by its own name, read from the database."""

    await IdentityService(session).delete_active_shop(
        shop_id=uuid.UUID(principal.active_shop_id),
        confirm_shop_name=payload.confirm_shop_name,
    )
