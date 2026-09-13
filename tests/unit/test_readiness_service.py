import pytest


@pytest.mark.anyio
async def test_readiness_reports_dependency_failure_without_hiding_it():
    from ecom_be.modules.health.services import HealthService

    async def database_probe():
        return True

    async def redis_probe():
        return False

    result = await HealthService().readiness(database_probe, redis_probe)

    assert result.status == "not_ready"
    assert result.dependencies == {"database": "ok", "redis": "unavailable"}


@pytest.mark.anyio
async def test_readiness_logs_probe_failure_without_exception_details(caplog):
    from ecom_be.modules.health.services import HealthService

    failure_details = "probe failure details"

    async def database_probe():
        raise RuntimeError(failure_details)

    async def redis_probe():
        return True

    result = await HealthService().readiness(database_probe, redis_probe)

    assert result.status == "not_ready"
    assert result.dependencies == {"database": "unavailable", "redis": "ok"}
    assert "database" in caplog.text
    assert failure_details not in caplog.text
