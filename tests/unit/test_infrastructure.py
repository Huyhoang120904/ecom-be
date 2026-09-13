import pytest
from pydantic import PostgresDsn, RedisDsn


def _database_url_value() -> PostgresDsn:
    return PostgresDsn.build(
        scheme="postgresql+asyncpg",
        host="localhost",
        port=5432,
        path="ecommerce",
    )


def _redis_url_value() -> RedisDsn:
    return RedisDsn.build(scheme="redis", host="localhost", port=6379, path="0")


@pytest.mark.anyio
async def test_db_session_dependency_yields_one_session_without_committing(monkeypatch):
    from ecom_be.infrastructure.db import session as db_session

    class FakeSession:
        committed = False

    fake_session = FakeSession()

    class SessionContext:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

    class SessionFactory:
        def __call__(self):
            return SessionContext()

    monkeypatch.setattr(db_session, "SessionFactory", SessionFactory())

    yielded_sessions = [session async for session in db_session.get_db_session()]

    assert yielded_sessions == [fake_session]
    assert fake_session.committed is False


def test_redis_client_factory_uses_decoding_and_configured_url(monkeypatch):
    from ecom_be.config.settings import Settings
    from ecom_be.infrastructure.cache import redis as redis_module

    captured = {}
    client = object()

    def fake_from_url(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return client

    monkeypatch.setattr(redis_module, "from_url", fake_from_url)
    settings = Settings(
        database_url=_database_url_value(), redis_url=_redis_url_value()
    )

    result = redis_module.create_redis_client(settings)

    assert result is client
    assert captured == {
        "url": str(_redis_url_value()),
        "kwargs": {"decode_responses": True},
    }


def test_database_engine_factory_uses_async_url_and_pre_ping(monkeypatch):
    from ecom_be.config.settings import Settings
    from ecom_be.infrastructure.db import session as db_session

    captured = {}
    engine = object()

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return engine

    monkeypatch.setattr(db_session, "create_async_engine", fake_create_async_engine)
    settings = Settings(
        database_url=_database_url_value(), redis_url=_redis_url_value()
    )

    result = db_session.create_db_engine(settings)

    assert result is engine
    assert captured == {
        "url": str(_database_url_value()),
        "kwargs": {"pool_pre_ping": True},
    }


@pytest.mark.anyio
async def test_database_probe_executes_a_lightweight_query():
    from ecom_be.api.deps import database_probe

    executed_statements = []

    class FakeSession:
        async def execute(self, statement):
            executed_statements.append(str(statement))

    assert await database_probe(FakeSession()) is True
    assert executed_statements == ["SELECT 1"]


@pytest.mark.anyio
async def test_redis_probe_calls_ping():
    from ecom_be.api.deps import redis_probe

    class FakeRedis:
        ping_calls = 0

        async def ping(self):
            self.ping_calls += 1
            return True

    client = FakeRedis()

    assert await redis_probe(client) is True
    assert client.ping_calls == 1
