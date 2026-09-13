"""The caller's own account: read, partial update, and deactivation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.api.deps import get_application_db_session, get_current_principal
from ecom_be.api.principal import Principal
from ecom_be.api.v1.identity.common import _me_data
from ecom_be.schemas.common import BaseResponse
from ecom_be.schemas.identity import (
    DeactivateRequest,
    MeData,
    ProfileUpdateRequest,
)
from ecom_be.services.account_service import AccountService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me", response_model=BaseResponse[MeData])
async def me(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> BaseResponse[MeData]:
    service = AccountService(session)
    user, shop, memberships, permissions = await service.me(
        user_id=uuid.UUID(principal.user_id),
        shop_id=uuid.UUID(principal.active_shop_id),
    )
    return BaseResponse[MeData](
        status_code=status.HTTP_200_OK,
        data=_me_data(user, shop, memberships, permissions, request),
    )


@router.patch("/me", response_model=BaseResponse[MeData])
async def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> BaseResponse[MeData]:
    """Update only the supplied keys, so an omitted field is left alone."""

    service = AccountService(session)
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    await service.update_profile(user_id=uuid.UUID(principal.user_id), changes=changes)
    user, shop, memberships, permissions = await service.me(
        user_id=uuid.UUID(principal.user_id),
        shop_id=uuid.UUID(principal.active_shop_id),
    )
    return BaseResponse[MeData](
        status_code=status.HTTP_200_OK,
        data=_me_data(user, shop, memberships, permissions, request),
    )


@router.post("/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate(
    payload: DeactivateRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> None:
    """Retire the account, confirmed by its password. One-way."""

    await AccountService(session).deactivate(
        user_id=uuid.UUID(principal.user_id), password=payload.password
    )
