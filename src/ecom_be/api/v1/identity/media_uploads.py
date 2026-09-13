"""The caller's avatar: upload and removal."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.api.deps import (
    get_application_db_session,
    get_current_principal,
    get_optional_redis_client,
)
from ecom_be.api.principal import Principal
from ecom_be.api.v1.identity.common import _client_key, _me_data, me_response
from ecom_be.api.v1.media import get_media_service
from ecom_be.schemas.common import BaseResponse
from ecom_be.schemas.identity import MeData
from ecom_be.services.account_service import AccountService
from ecom_be.services.media_service import MediaService
from ecom_be.services.rate_limit_service import (
    UPLOAD_LIMIT,
    UPLOAD_WINDOW_SECONDS,
    RateLimitStore,
    enforce_rate_limit,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/me/avatar", response_model=BaseResponse[MeData])
async def upload_avatar(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    media: Annotated[MediaService, Depends(get_media_service)],
    file: Annotated[UploadFile, File()],
    redis: Annotated[RateLimitStore | None, Depends(get_optional_redis_client)] = None,
) -> BaseResponse[MeData]:
    """Replace the caller's avatar.

    The previous object is left in place rather than deleted: its key is content
    addressed, so a client showing the old URL keeps working until it refetches, and
    the digest key means a revert to a previous image is free.
    """

    await enforce_rate_limit(
        redis,
        key=_client_key(request, "upload"),
        limit=UPLOAD_LIMIT,
        window_seconds=UPLOAD_WINDOW_SECONDS,
    )
    payload = await file.read()
    service = AccountService(session)
    key = await media.store_avatar(
        user_id=uuid.UUID(principal.user_id),
        image_bytes=payload,
        declared_content_type=file.content_type or "application/octet-stream",
    )
    await service.set_avatar(user_id=uuid.UUID(principal.user_id), key=key)

    user, shop, memberships, permissions = await service.me(
        user_id=uuid.UUID(principal.user_id),
        shop_id=uuid.UUID(principal.active_shop_id),
    )
    return me_response(_me_data(user, shop, memberships, permissions, request))


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def delete_avatar(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    media: Annotated[MediaService, Depends(get_media_service)],
) -> None:
    """Remove the caller's avatar. Idempotent: a second call is also 204."""

    service = AccountService(session)
    user = await service.get_user(uuid.UUID(principal.user_id))
    if user.avatar_key:
        await media.delete(user.avatar_key)
    await service.set_avatar(user_id=uuid.UUID(principal.user_id), key=None)
