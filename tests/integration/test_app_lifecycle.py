import pytest


@pytest.mark.anyio
async def test_app_lifecycle_owns_and_closes_one_redis_client(monkeypatch):
    import ecom_be.main as main_module

    class FakeRedisClient:
        close_calls = 0

        async def aclose(self):
            self.close_calls += 1

    client = FakeRedisClient()
    factory_calls = 0

    class FakeEngine:
        dispose_calls = 0

        async def dispose(self):
            self.dispose_calls += 1

    engine = FakeEngine()

    def fake_create_redis_client(settings):
        nonlocal factory_calls
        factory_calls += 1
        return client

    monkeypatch.setattr(main_module, "create_redis_client", fake_create_redis_client)
    monkeypatch.setattr(main_module, "engine", engine)
    application = main_module.create_app()

    async with application.router.lifespan_context(application):
        assert application.state.redis_client is client
        assert application.state.redis is client
        assert factory_calls == 1
        assert client.close_calls == 0
        assert engine.dispose_calls == 0

    assert client.close_calls == 1
    assert engine.dispose_calls == 1
