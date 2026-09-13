"""Identity HTTP transport: shared response mapping and cookie handling.

Every route module in this package builds its payloads through these mappers, so
a response shape is defined once. Cookie handling is here for the same reason:
``SameSite``, ``Path``, and ``Secure`` belong in one place rather than threaded
through a use case that would then need to know about HTTP.

The ``*_response`` builders wrap a payload in ``BaseResponse`` and take the status
code explicitly, so the body always echoes the code the route actually returned
(``201`` for registration, and the readiness route's ``503``) rather than a default
that happens to match most of them.
"""

from __future__ import annotations

from fastapi import Request, Response, status

from ecom_be.api.media_urls import avatar_url, background_url
from ecom_be.models.identity import Role, Shop, User
from ecom_be.schemas.common import BaseResponse
from ecom_be.schemas.identity import (
    MeData,
    MembershipData,
    RoleData,
    SessionData,
    ShopData,
    UserData,
)
from ecom_be.services.identity_service import Session

REFRESH_COOKIE = "ecom_refresh"

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


def session_response(data: SessionData) -> BaseResponse[SessionData]:
    """Envelop a sign-in payload. Registration is the reason the code is explicit."""

    return BaseResponse[SessionData](status_code=status.HTTP_201_CREATED, data=data)


def me_response(data: MeData) -> BaseResponse[MeData]:
    return BaseResponse[MeData](status_code=status.HTTP_200_OK, data=data)


def shop_response(data: ShopData) -> BaseResponse[ShopData]:
    return BaseResponse[ShopData](status_code=status.HTTP_200_OK, data=data)
