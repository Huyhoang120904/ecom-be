"""Fixtures shared by the catalog and product API tests.

A ``Seller`` is a registered account with its own shop and a bearer token. The
``db`` tests share one transaction, so a seller created here is visible to the
endpoint under test and rolled back afterwards.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from catalog_helpers import Seed, load_seed
from httpx import AsyncClient
from sqlalchemy import text

from app.repositories import membership_repository

PASSWORD = "a-perfectly-fine-password"


@dataclass(frozen=True)
class Seller:
    email: str
    shop_id: uuid.UUID
    headers: dict[str, str]


RegisterSeller = Callable[..., Awaitable[Seller]]


@pytest.fixture
def register_seller(db_async_client: AsyncClient) -> RegisterSeller:
    """Register an account (which creates its shop and makes it ``owner``)."""

    async def register(
        email: str = "owner@example.com", shop_name: str = "Test Shop"
    ) -> Seller:
        created = await db_async_client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "full_name": "Test Seller",
                "shop_name": shop_name,
            },
        )
        assert created.status_code == 201, created.text
        login = await db_async_client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        headers = {"authorization": f"Bearer {login.json()['data']['access_token']}"}
        me = await db_async_client.get("/api/v1/auth/me", headers=headers)
        shop_id = uuid.UUID(me.json()["data"]["active_shop"]["id"])
        return Seller(email=email, shop_id=shop_id, headers=headers)

    return register


@pytest.fixture
async def empty_catalog(db_session) -> None:
    """Remove the seeded sample catalog for the length of one test.

    The catalog migration seeds sample rows (a ``ram`` attribute, a ``Nike`` brand, a
    category tree...). A test about creating and rejecting those same names must not
    depend on them. The delete runs inside the test's own transaction, which is rolled
    back afterwards, so the seed itself is never touched. The seed has its own test.
    """

    for table in ("category_attributes", "attribute_options", "attributes", "brands"):
        await db_session.execute(text(f"DELETE FROM {table}"))
    # ``categories.parent_id`` is RESTRICT, so peel the tree from its leaves upward.
    for _ in range(10):
        await db_session.execute(
            text(
                "DELETE FROM categories c WHERE NOT EXISTS "
                "(SELECT 1 FROM categories k WHERE k.parent_id = c.id)"
            )
        )


@pytest.fixture
async def owner(register_seller: RegisterSeller) -> Seller:
    return await register_seller()


@pytest.fixture
def demote(db_session):
    """Change a seller's role in their own shop, effective on their next request."""

    async def _demote(seller: Seller, role_key: str) -> None:
        await membership_repository.set_membership_role_by_key(
            db_session,
            user_email=seller.email,
            shop_id=seller.shop_id,
            role_key=role_key,
        )

    return _demote


@pytest.fixture
async def seeded(db_session) -> Seed:
    """The ids of the seeded sample catalog (``ao-thun``, ``laptop``, ...)."""

    return await load_seed(db_session)
