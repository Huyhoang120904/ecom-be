"""The identity HTTP contract.

This file is transport and nothing else. It binds dependencies, turns a service
result into a response model, and owns the refresh cookie. Cookie handling lives
here because it *is* transport: ``SameSite``, ``Path``, and ``Secure`` belong in one
place, not threaded through a use case that would then need to know about HTTP.

No handler here builds an error response. A domain error is raised by the service
and rendered by the single handler in ``core/errors.py``, so the failure shape is
defined once.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.api.deps import (
    get_application_db_session,
    get_current_principal,
    get_optional_redis_client,
    require_permissions,
)
from ecom_be.api.media_urls import avatar_url, background_url
from ecom_be.modules.identity.models import Role, Shop, User
from ecom_be.modules.identity.principal import Principal
from ecom_be.modules.identity.schemas.request import (
    DeactivateRequest,
    DeleteShopRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    ShopUpdateRequest,
    SwitchShopRequest,
)
from ecom_be.modules.identity.schemas.response import (
    MeData,
    MeEnvelope,
    MembershipData,
    RoleData,
    SessionData,
    SessionEnvelope,
    ShopData,
    ShopEnvelope,
    UserData,
)
from ecom_be.modules.identity.services import (
    LOGIN_LIMIT,
    LOGIN_WINDOW_SECONDS,
    REGISTER_LIMIT,
    REGISTER_WINDOW_SECONDS,
    UPLOAD_LIMIT,
    UPLOAD_WINDOW_SECONDS,
    IdentityService,
    RateLimitStore,
    Session,
    enforce_rate_limit,
)
from ecom_be.modules.media.router import get_media_service
from ecom_be.modules.media.services import MediaService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
shops_router = APIRouter(prefix="/api/v1/shops", tags=["shops"])

REFRESH_COOKIE = "ecom_refresh"
# Scoping the cookie to the auth paths keeps the credential off every other
# request, so a future endpoint cannot leak it into a log by accident.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _client_key(request: Request, bucket: str) -> str:
    """A rate-limit key scoped to one client and one action."""

    client = request.client
    host = client.host if client is not None else "unknown"
    return f"{bucket}:{host}"


def _set_refresh_cookie(
    response: Response, request: Request, token: str, max_age: int
) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        # Secure is omitted only for local development, where the API is plain HTTP
        # and a Secure cookie would simply never be sent back.
        secure=settings.environment != "development",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def _role_data(role: Role) -> RoleData:
    return RoleData(key=role.key, name=role.name)


def _user_data(user: User, request: Request) -> UserData:
    return UserData(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        bio=user.bio,
        phone=user.phone,
        job_title=user.job_title,
        avatar_url=avatar_url(user, request),
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def _shop_data(shop: Shop, request: Request) -> ShopData:
    return ShopData(
        id=shop.id,
        name=shop.name,
        slug=shop.slug,
        description=shop.description,
        contact_email=shop.contact_email,
        contact_phone=shop.contact_phone,
        website=shop.website,
        background_url=background_url(shop, request),
    )


def _membership_data(
    memberships: list[tuple[Shop, Role]], request: Request
) -> list[MembershipData]:
    return [
        MembershipData(shop=_shop_data(shop, request), role=_role_data(role))
        for shop, role in memberships
    ]


def _session_data(session: Session, request: Request) -> SessionData:
    """Build the response payload from a service result.

    The media URLs are derived here from the stored object keys, so the deployment's
    storage layout never becomes part of the contract.
    """

    return SessionData(
        access_token=session.access_token,
        token_type="bearer",
        expires_in=session.expires_in,
        user=_user_data(session.user, request),
        active_shop=_shop_data(session.active_shop, request),
        memberships=_membership_data(session.memberships, request),
        permissions=session.permissions,
    )


def _me_data(
    user: User,
    shop: Shop,
    memberships: list[tuple[Shop, Role]],
    permissions: list[str],
    request: Request,
) -> MeData:
    return MeData(
        user=_user_data(user, request),
        active_shop=_shop_data(shop, request),
        memberships=_membership_data(memberships, request),
        permissions=permissions,
    )


@router.post(
    "/register",
    response_model=SessionEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    redis: Annotated[RateLimitStore | None, Depends(get_optional_redis_client)],
) -> SessionEnvelope:
    """Create an account and its first shop, then sign in."""

    await enforce_rate_limit(
        redis,
        key=_client_key(request, "register"),
        limit=REGISTER_LIMIT,
        window_seconds=REGISTER_WINDOW_SECONDS,
    )
    result = await IdentityService(session).register(
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
    return SessionEnvelope(data=_session_data(result, request))


@router.post("/login", response_model=SessionEnvelope)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    redis: Annotated[RateLimitStore | None, Depends(get_optional_redis_client)],
) -> SessionEnvelope:
    await enforce_rate_limit(
        redis,
        key=_client_key(request, "login"),
        limit=LOGIN_LIMIT,
        window_seconds=LOGIN_WINDOW_SECONDS,
    )
    result = await IdentityService(session).login(
        email=payload.email, password=payload.password
    )
    _set_refresh_cookie(
        response,
        request,
        result.refresh_token,
        request.app.state.settings.refresh_token_ttl_seconds,
    )
    return SessionEnvelope(data=_session_data(result, request))


@router.post("/refresh", response_model=SessionEnvelope)
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> SessionEnvelope:
    """Rotate the refresh cookie and issue a new access token."""

    result = await IdentityService(session).refresh(request.cookies.get(REFRESH_COOKIE))
    _set_refresh_cookie(
        response,
        request,
        result.refresh_token,
        request.app.state.settings.refresh_token_ttl_seconds,
    )
    return SessionEnvelope(data=_session_data(result, request))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> None:
    """End the session. Always 204: a client leaving has nothing to learn."""

    await IdentityService(session).logout(request.cookies.get(REFRESH_COOKIE))
    _clear_refresh_cookie(response)


@router.post("/switch-shop", response_model=SessionEnvelope)
async def switch_shop(
    payload: SwitchShopRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> SessionEnvelope:
    result = await IdentityService(session).switch_shop(
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
    return SessionEnvelope(data=_session_data(result, request))


@router.get("/me", response_model=MeEnvelope)
async def me(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> MeEnvelope:
    service = IdentityService(session)
    user, shop, memberships, permissions = await service.me(
        user_id=uuid.UUID(principal.user_id),
        shop_id=uuid.UUID(principal.active_shop_id),
    )
    return MeEnvelope(data=_me_data(user, shop, memberships, permissions, request))


@router.patch("/me", response_model=MeEnvelope)
async def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> MeEnvelope:
    """Update only the supplied keys, so an omitted field is left alone."""

    service = IdentityService(session)
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    await service.update_profile(user_id=uuid.UUID(principal.user_id), changes=changes)
    user, shop, memberships, permissions = await service.me(
        user_id=uuid.UUID(principal.user_id),
        shop_id=uuid.UUID(principal.active_shop_id),
    )
    return MeEnvelope(data=_me_data(user, shop, memberships, permissions, request))


@router.post("/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate(
    payload: DeactivateRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
) -> None:
    """Retire the account, confirmed by its password. One-way."""

    await IdentityService(session).deactivate(
        user_id=uuid.UUID(principal.user_id), password=payload.password
    )


@router.post("/me/avatar", response_model=MeEnvelope)
async def upload_avatar(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    media: Annotated[MediaService, Depends(get_media_service)],
    file: Annotated[UploadFile, File()],
    redis: Annotated[RateLimitStore | None, Depends(get_optional_redis_client)] = None,
) -> MeEnvelope:
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
    service = IdentityService(session)
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
    return MeEnvelope(data=_me_data(user, shop, memberships, permissions, request))


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def delete_avatar(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_application_db_session)],
    media: Annotated[MediaService, Depends(get_media_service)],
) -> None:
    """Remove the caller's avatar. Idempotent: a second call is also 204."""

    service = IdentityService(session)
    user = await service.get_user(uuid.UUID(principal.user_id))
    if user.avatar_key:
        await media.delete(user.avatar_key)
    await service.set_avatar(user_id=uuid.UUID(principal.user_id), key=None)


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


__all__ = ["REFRESH_COOKIE", "REFRESH_COOKIE_PATH", "router", "shops_router"]
