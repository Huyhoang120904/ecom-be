"""What a sign-in produces, and the one place a session is minted.

``issue_session`` mints an access token, persists the refresh row, and assembles the
result. It deliberately does *not* commit: the caller owns the transaction boundary,
which is what lets registration keep four writes in one transaction.

``refresh_token`` is a field on ``Session`` and nowhere else on the way out: the
router turns it into an httpOnly cookie and nothing else ever sees it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ecom_be.config.settings import Settings
from ecom_be.errors.identity import NotAMember
from ecom_be.models.identity import Role, Shop, User
from ecom_be.repositories import membership_repository, refresh_token_repository
from ecom_be.utils import identity as utils


@dataclass(frozen=True, slots=True)
class Session:
    """What a successful sign-in produces."""

    access_token: str
    expires_in: int
    user: User
    active_shop: Shop
    memberships: list[tuple[Shop, Role]]
    permissions: list[str]
    refresh_token: str


async def issue_session(
    session: AsyncSession,
    settings: Settings,
    user: User,
    shop_id: uuid.UUID,
    *,
    family_id: uuid.UUID | None = None,
) -> Session:
    """Mint an access token, persist the refresh row, and assemble the result.

    Does not commit: the caller decides the transaction boundary, which is what
    lets ``register`` keep four writes in one transaction.
    """

    membership = await membership_repository.find_membership(
        session, user_id=user.id, shop_id=shop_id
    )
    if membership is None:
        raise NotAMember
    shop, _role = membership

    resolved = await membership_repository.effective_permissions(
        session, user_id=user.id, shop_id=shop_id
    )
    permissions = resolved[2] if resolved is not None else []

    access_token = utils.issue_access_token(
        settings, user_id=str(user.id), active_shop_id=str(shop_id)
    )
    raw_refresh, digest = utils.new_refresh_token()
    await refresh_token_repository.create_refresh_token(
        session,
        user_id=user.id,
        active_shop_id=shop_id,
        token_hash=digest,
        expires_at=datetime.now(UTC)
        + timedelta(seconds=settings.refresh_token_ttl_seconds),
        family_id=family_id,
    )
    memberships = await membership_repository.list_memberships(session, user.id)
    return Session(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        user=user,
        active_shop=shop,
        memberships=memberships,
        permissions=permissions,
        refresh_token=raw_refresh,
    )
