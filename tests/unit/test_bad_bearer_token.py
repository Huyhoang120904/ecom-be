"""Contract: a token that is not a valid access token is a ``401``, never a ``500``.

Runs without a database: the token is refused before any lookup. Covers the shapes a
client can actually send -- not a JWT at all, a JWT that is not ours, a wrong scheme.
"""

from __future__ import annotations

import jwt
import pytest

pytestmark = pytest.mark.anyio

ROUTES = ("/api/v1/auth/me", "/api/v1/products", "/api/v1/catalog/brands")


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer nope",
        "Bearer a.b.c",
        "Bearer ",
        "Basic dXNlcjpwYXNz",
        "nope",
        "Bearer "
        + jwt.encode({"sub": "x"}, "another-secret-long-enough-for-hs256", "HS256"),
    ],
)
async def test_an_invalid_token_is_unauthenticated(async_client, route, authorization):
    response = await async_client.get(route, headers={"authorization": authorization})

    assert response.status_code == 401
    assert response.json() == {
        "error": "invalid_token",
        "message": "Authentication required",
    }
