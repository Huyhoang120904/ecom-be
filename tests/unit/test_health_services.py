def test_liveness_service_returns_healthy_payload():
    from app.services.health_service import HealthService

    result = HealthService().liveness()

    assert result.status == "ok"
    assert result.service == "ecom-be"
