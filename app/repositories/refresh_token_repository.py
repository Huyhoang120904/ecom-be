"""Every statement against ``refresh_tokens``.

Revocation is a state (``revoked_at``) rather than a deleted row, so a token that was
already rotated can still be recognized as reused instead of merely absent. Nothing
here commits: the service decides where a transaction ends.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import RefreshToken


def _rowcount(result: object) -> int:
    """Read a DML row count.

    SQLAlchemy types ``AsyncSession.execute`` as returning ``Result`` even for an
    ``update`` or ``delete``, where the runtime object is a ``CursorResult`` and does
    carry ``rowcount``. Narrowing in one place keeps the cast out of every call site.
    """

    if isinstance(result, CursorResult):
        return int(result.rowcount or 0)
    return 0


async def create_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    active_shop_id: uuid.UUID | None,
    token_hash: str,
    expires_at: datetime,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> RefreshToken:
    token = RefreshToken(
        user_id=user_id,
        active_shop_id=active_shop_id,
        token_hash=token_hash,
        family_id=family_id or uuid.uuid4(),
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.add(token)
    await session.flush()
    return token


async def find_refresh_token(
    session: AsyncSession, token_hash: str
) -> RefreshToken | None:
    return (
        await session.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
    ).first()


async def revoke_refresh_token(
    session: AsyncSession, token: RefreshToken, replaced_by: RefreshToken | None = None
) -> None:
    token.revoked_at = datetime.now(UTC)
    if replaced_by is not None:
        token.replaced_by_id = replaced_by.id
    await session.flush()


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> int:
    """Revoke every unrevoked token in one family. Returns how many were revoked."""

    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    return _rowcount(result)


async def revoke_all_families_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> int:
    """Revoke every session an account holds, not just the current one.

    Used by deactivation: a deactivated account must not keep a live session
    anywhere.
    """

    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return _rowcount(result)


async def revoke_families_for_shop(session: AsyncSession, shop_id: uuid.UUID) -> int:
    """Revoke the sessions whose active shop is this one.

    Deleting a shop ends the sessions that were scoped to it, which is what makes
    their next request a clean "that shop is gone" rather than a lingering token
    pointing at nothing.
    """

    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.active_shop_id == shop_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    return _rowcount(result)


async def list_unrevoked_family(
    session: AsyncSession, family_id: uuid.UUID
) -> list[RefreshToken]:
    rows = await session.execute(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    return list(rows.scalars())


async def delete_expired_refresh_tokens(session: AsyncSession) -> int:
    """Lazily prune rows past expiry.

    Called by the login and refresh paths rather than by a scheduled job: those are
    the two moments the table is already being written, so the cleanup rides on work
    that is happening anyway.
    """

    result = await session.execute(
        delete(RefreshToken).where(RefreshToken.expires_at <= datetime.now(UTC))
    )
    return _rowcount(result)
