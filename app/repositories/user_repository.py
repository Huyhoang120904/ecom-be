"""Every statement the identity layer runs against ``users``.

Two rules hold throughout:

* This is the only layer that runs a statement. A service decides *what* should
  happen; this file is *how* it reaches the database.
* Nothing here commits. The request-scoped session is yielded with no implicit
  commit, so a service decides where a transaction ends. A repository that commits
  would make a multi-step use case impossible to keep atomic.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User


async def find_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Find a live user by email.

    ``email`` is a ``citext`` column, so the comparison is case-insensitive without
    this function doing anything, and a mixed-case row cannot exist because of the
    ``users_email_lower`` check.
    """

    statement: Select[tuple[User]] = select(User).where(
        User.email == email, User.deleted_at.is_(None)
    )
    return (await session.scalars(statement)).first()


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return (
        await session.scalars(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).first()


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str,
    full_name: str,
) -> User:
    user = User(email=email, password_hash=password_hash, full_name=full_name)
    session.add(user)
    await session.flush()
    return user


async def set_last_login(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(last_login_at=datetime.now(UTC))
    )


async def deactivate_user(session: AsyncSession, user: User) -> None:
    """Retire an account's ability to sign in without releasing its email."""

    user.deactivated_at = datetime.now(UTC)
    await session.flush()


async def soft_delete_user(session: AsyncSession, user: User) -> None:
    """Retire an account and release its email address for reuse."""

    user.deleted_at = datetime.now(UTC)
    await session.flush()


async def update_user_profile(
    session: AsyncSession, user: User, changes: dict[str, str | None]
) -> User:
    """Apply only the keys present in ``changes``.

    The caller is responsible for having decided which keys were supplied; an
    omitted key never reaches here, which is what makes "leave it alone" and "clear
    it" different outcomes rather than the same one.
    """

    for field, value in changes.items():
        setattr(user, field, value)
    await session.flush()
    return user


async def set_user_avatar_key(
    session: AsyncSession, user: User, key: str | None
) -> None:
    user.avatar_key = key
    user.avatar_updated_at = datetime.now(UTC) if key is not None else None
    await session.flush()
