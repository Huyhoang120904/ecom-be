"""Management CLI commands for ecom-be."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import SessionFactory
from app.infrastructure.security.passwords import hash_password
from app.models.identity import User
from app.repositories import membership_repository, role_repository, user_repository
from app.utils.identity import normalize_email, normalize_name, validate_password


async def create_admin_account(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
) -> User:
    """Bootstrap or promote an account to platform administrator."""

    norm_email = normalize_email(email)
    norm_name = normalize_name(full_name, field="full_name")
    validate_password(password)

    user = await user_repository.find_user_by_email(session, norm_email)
    if user is None:
        user = await user_repository.create_user(
            session,
            email=norm_email,
            password_hash=hash_password(password),
            full_name=norm_name,
        )

    sys_admin_role = await role_repository.get_sys_admin_role(session)
    existing_membership = await membership_repository.find_platform_membership(
        session, user.id
    )
    if existing_membership is None:
        await membership_repository.create_membership(
            session,
            user_id=user.id,
            shop_id=None,
            role_id=sys_admin_role.id,
        )
    await session.commit()
    return user


def build_parser() -> argparse.ArgumentParser:
    """The command line surface, built in one place a test can interrogate."""

    parser = argparse.ArgumentParser(description="E-commerce backend admin CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    admin_parser = subparsers.add_parser(
        "create-admin", help="Bootstrap a platform administrator"
    )
    admin_parser.add_argument("--email", required=True, help="Admin email address")
    admin_parser.add_argument("--password", required=True, help="Admin password")
    admin_parser.add_argument("--full-name", required=True, help="Admin full name")
    return parser


async def _create_admin_from_args(args: argparse.Namespace) -> None:
    async with SessionFactory() as session:
        user = await create_admin_account(
            session,
            email=args.email,
            password=args.password,
            full_name=args.full_name,
        )
        print(
            f"Platform administrator created successfully: {user.email} (ID: {user.id})"
        )


def main(argv: Sequence[str] | None = None) -> None:
    """Run one command. ``argv`` defaults to ``sys.argv[1:]``, as argparse expects."""

    args = build_parser().parse_args(argv)
    if args.command == "create-admin":
        asyncio.run(_create_admin_from_args(args))


if __name__ == "__main__":
    main()
