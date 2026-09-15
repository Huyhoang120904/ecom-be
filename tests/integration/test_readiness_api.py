import pytest


@pytest.mark.anyio
async def test_readiness_endpoint_returns_ok_for_healthy_dependencies(async_client):
    from app.api.deps import get_database_probe, get_redis_probe
    from app.main import app

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
        "status_code": 200,
        "message": "Success",
        "data": {
            "status": "ok",
            "dependencies": {"database": "ok", "redis": "ok"},
        },
    }


@pytest.mark.anyio
async def test_readiness_endpoint_returns_503_for_unavailable_dependency(async_client):
    from app.api.deps import get_database_probe, get_redis_probe
    from app.main import app

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
    # The body is the same envelope at 503 as at 200, and its ``status_code`` echoes
    # the code the route returned, so a client can read the outcome from the body it
    # already has. The shape is identical, so the unwrap is still unconditional.
    assert response.json() == {
        "status_code": 503,
        "message": "Success",
        "data": {
            "status": "not_ready",
            "dependencies": {"database": "ok", "redis": "unavailable"},
        },
    }


@pytest.mark.anyio
async def test_readiness_endpoint_uses_the_probe_a_dependency_override_provides(
    async_client,
):
    from app.api.deps import get_database_probe, get_redis_probe
    from app.main import app

    async def database_probe():
        return True

    async def redis_probe():
        return True

    # The override replaces the factory, so it must yield a probe: a callable that
    # returns an awaitable bool. This is the shape ``get_database_probe`` has.
    app.dependency_overrides[get_database_probe] = lambda: database_probe
    app.dependency_overrides[get_redis_probe] = lambda: redis_probe
    try:
        response = await async_client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


@pytest.mark.anyio
async def test_an_override_that_yields_a_value_instead_of_a_probe_reports_unavailable(
    async_client,
):
    """A resolved bool is not a probe, and the endpoint must say so rather than crash.

    This pins the removal of the old ``_as_probe`` shim, which widened production
    code so a test could override a dependency with a plain boolean. A dependency
    that resolves to ``True`` now surfaces as an unavailable dependency, because a
    value cannot be called.
    """

    from app.api.deps import get_database_probe, get_redis_probe
    from app.main import app

    app.dependency_overrides[get_database_probe] = lambda: True
    app.dependency_overrides[get_redis_probe] = lambda: True
    try:
        response = await async_client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["data"] == {
        "status": "not_ready",
        "dependencies": {"database": "unavailable", "redis": "unavailable"},
    }
