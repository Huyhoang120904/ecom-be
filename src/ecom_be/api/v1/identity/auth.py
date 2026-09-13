"""Authentication routes: registration, sign-in, rotation, sign-out, shop switch."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.api.deps import (
    get_application_db_session,
    get_current_principal,
    get_optional_redis_client,
)
from ecom_be.api.principal import Principal
from ecom_be.api.v1.identity.common import (
    REFRESH_COOKIE,
    _clear_refresh_cookie,
    _client_key,
    _session_data,
    _set_refresh_cookie,
    session_response,
)
from ecom_be.schemas.common import BaseResponse
from ecom_be.schemas.identity import (
    LoginRequest,
    RegisterRequest,
    SessionData,
    SwitchShopRequest,
)
from ecom_be.services.auth_service import AuthService
from ecom_be.services.rate_limit_service import (
    LOGIN_LIMIT,
    LOGIN_WINDOW_SECONDS,
    REGISTER_LIMIT,
    REGISTER_WINDOW_SECONDS,
    RateLimitStore,
    enforce_rate_limit,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=BaseResponse[SessionData],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    redis: Annotated[RateLimitStore | None, Depends(get_optional_redis_client)],
) -> BaseResponse[SessionData]:
    """Create an account and its first shop, then sign in."""

    await enforce_rate_limit(
        redis,
        key=_client_key(request, "register"),
        limit=REGISTER_LIMIT,
        window_seconds=REGISTER_WINDOW_SECONDS,
    )
    result = await AuthService(session).register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        shop_name=payload.shop_name,
    )
    _set_refresh_cookie(
        response,
        request,
        result.refresh_token,
        request.app.state.settings.refresh_token_ttl_seconds,
    )
    return session_response(_session_data(result, request))


@router.post("/login", response_model=BaseResponse[SessionData])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    redis: Annotated[RateLimitStore | None, Depends(get_optional_redis_client)],
) -> BaseResponse[SessionData]:
    await enforce_rate_limit(
        redis,
        key=_client_key(request, "login"),
        limit=LOGIN_LIMIT,
        window_seconds=LOGIN_WINDOW_SECONDS,
    )
    result = await AuthService(session).login(
        email=payload.email, password=payload.password
    )
    _set_refresh_cookie(
        response,
        request,
        result.refresh_token,
        request.app.state.settings.refresh_token_ttl_seconds,
    )
    return session_response(_session_data(result, request))


@router.post("/refresh", response_model=BaseResponse[SessionData])
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> BaseResponse[SessionData]:
    """Rotate the refresh cookie and issue a new access token."""

    result = await AuthService(session).refresh(request.cookies.get(REFRESH_COOKIE))
    _set_refresh_cookie(
        response,
        request,
        result.refresh_token,
        request.app.state.settings.refresh_token_ttl_seconds,
    )
    return session_response(_session_data(result, request))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> None:
    """End the session. Always 204: a client leaving has nothing to learn."""

    await AuthService(session).logout(request.cookies.get(REFRESH_COOKIE))
    _clear_refresh_cookie(response)


@router.post("/switch-shop", response_model=BaseResponse[SessionData])
async def switch_shop(
    payload: SwitchShopRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> BaseResponse[SessionData]:
    result = await AuthService(session).switch_shop(
        user_id=uuid.UUID(principal.user_id),
        shop_id=payload.shop_id,
        refresh_token=request.cookies.get(REFRESH_COOKIE),
    )
    _set_refresh_cookie(
        response,
        request,
        result.refresh_token,
        request.app.state.settings.refresh_token_ttl_seconds,
    )
    return session_response(_session_data(result, request))
