"""Contract: the management CLI commands.

Two layers are covered. The wiring tests run the real parser and dispatch with a
stubbed session factory, because a flag that never reaches the service is invisible
to a test that calls ``create_admin_account`` directly. The database test proves the
account and its platform membership actually land.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.cli import create_admin_account
from app.repositories import membership_repository

PASSWORD = "SuperSecretPassword123!"


class _StubSession:
    """The smallest async context manager the CLI's ``async with`` needs."""

    async def __aenter__(self) -> _StubSession:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def test_the_entry_point_forwards_parsed_flags_to_the_service(monkeypatch, capsys):
    """A dropped flag is a broken command, and this is what notices."""

    calls: list[dict[str, str]] = []

    async def fake_create_admin_account(session, *, email, password, full_name):
        calls.append({"email": email, "password": password, "full_name": full_name})
        return SimpleNamespace(email=email, id="11111111-1111-4111-8111-111111111111")

    monkeypatch.setattr(cli, "create_admin_account", fake_create_admin_account)
    monkeypatch.setattr(cli, "SessionFactory", _StubSession)

    cli.main(
        [
            "create-admin",
            "--email",
            "wired@example.com",
            "--password",
            PASSWORD,
            "--full-name",
            "Wired Admin",
        ]
    )

    assert calls == [
        {
            "email": "wired@example.com",
            "password": PASSWORD,
            "full_name": "Wired Admin",
        }
    ]
    assert "wired@example.com" in capsys.readouterr().out


def test_a_missing_flag_is_a_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["create-admin", "--email", "a@example.com", "--password", PASSWORD])

    assert excinfo.value.code == 2


def test_an_unknown_command_is_a_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["promote-everyone"])

    assert excinfo.value.code == 2


@pytest.mark.anyio
@pytest.mark.db
async def test_create_admin_account_creates_user_and_platform_membership(
    db_session: AsyncSession,
):
    user = await create_admin_account(
        db_session,
        email="cli_admin@example.com",
        password=PASSWORD,
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
        password=PASSWORD,
        full_name="CLI Administrator",
    )
    assert user2.id == user.id
