import pytest


@pytest.mark.anyio
async def test_liveness_endpoint_returns_ok(async_client):
    response = await async_client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
