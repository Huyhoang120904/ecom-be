"""Contract: the management CLI commands."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli import create_admin_account
from app.repositories import membership_repository

pytestmark = [pytest.mark.anyio, pytest.mark.db]


async def test_create_admin_account_creates_user_and_platform_membership(
    db_session: AsyncSession,
):
    user = await create_admin_account(
        db_session,
        email="cli_admin@example.com",
        password="SuperSecretPassword123!",
        full_name="CLI Administrator",
    )
    assert user.email == "cli_admin@example.com"

    platform_membership = await membership_repository.find_platform_membership(
        db_session, user.id
    )
    assert platform_membership is not None
    role, permissions = platform_membership
    assert role.key == "sys_admin"
    assert "platform:metrics:read" in permissions
    assert "platform:shops:manage" in permissions

    # Running it again is idempotent (doesn't fail or create duplicate membership)
    user2 = await create_admin_account(
        db_session,
        email="cli_admin@example.com",
        password="SuperSecretPassword123!",
        full_name="CLI Administrator",
    )
    assert user2.id == user.id
