def test_liveness_service_returns_healthy_payload():
    from ecom_be.modules.health.services import HealthService

    result = HealthService().liveness()

    assert result.status == "ok"
    assert result.service == "ecom-be"
