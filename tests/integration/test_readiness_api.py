import pytest


@pytest.mark.anyio
async def test_readiness_endpoint_returns_ok_for_healthy_dependencies(async_client):
    from ecom_be.api.deps import get_database_probe, get_redis_probe
    from ecom_be.main import app

    async def database_probe():
        return True

    async def redis_probe():
        return True

    app.dependency_overrides[get_database_probe] = lambda: database_probe
    app.dependency_overrides[get_redis_probe] = lambda: redis_probe
    try:
        response = await async_client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "dependencies": {"database": "ok", "redis": "ok"},
    }


@pytest.mark.anyio
async def test_readiness_endpoint_returns_503_for_unavailable_dependency(async_client):
    from ecom_be.api.deps import get_database_probe, get_redis_probe
    from ecom_be.main import app

    async def database_probe():
        return True

    async def redis_probe():
        return False

    app.dependency_overrides[get_database_probe] = lambda: database_probe
    app.dependency_overrides[get_redis_probe] = lambda: redis_probe
    try:
        response = await async_client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {"database": "ok", "redis": "unavailable"},
    }


@pytest.mark.anyio
async def test_readiness_endpoint_accepts_status_returning_dependency_overrides(
    async_client,
):
    from ecom_be.api.deps import get_database_probe, get_redis_probe
    from ecom_be.main import app

    async def database_probe():
        return True

    async def redis_probe():
        return True

    app.dependency_overrides[get_database_probe] = database_probe
    app.dependency_overrides[get_redis_probe] = redis_probe
    try:
        response = await async_client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
