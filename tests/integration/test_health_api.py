import json
import logging

import pytest


@pytest.mark.anyio
async def test_liveness_endpoint_returns_ok(async_client):
    response = await async_client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_unknown_route_uses_consistent_error_shape(async_client):
    response = await async_client.get("/does-not-exist")

    assert response.status_code == 404
    assert set(response.json()) == {"error", "message"}


@pytest.mark.anyio
async def test_request_validation_uses_safe_stable_error_response():
    from fastapi import Query
    from httpx import ASGITransport, AsyncClient

    from ecom_be.main import create_app

    application = create_app()

    async def validation_route(limit: int = Query(gt=0)):
        return {"limit": limit}

    application.add_api_route("/test-validation", validation_route, methods=["GET"])
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test-validation", params={"limit": "invalid"})

    assert response.status_code == 422
    assert response.json() == {
        "error": "validation_error",
        "message": "Request validation failed",
    }


@pytest.mark.anyio
async def test_http_exception_uses_stable_code_and_safe_message():
    from fastapi import HTTPException
    from httpx import ASGITransport, AsyncClient

    from ecom_be.main import create_app

    application = create_app()

    async def forbidden_route():
        raise HTTPException(status_code=403, detail="token=do-not-expose")

    application.add_api_route("/test-forbidden", forbidden_route, methods=["GET"])
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test-forbidden")

    assert response.status_code == 403
    assert response.json() == {"error": "forbidden", "message": "Forbidden"}


@pytest.mark.anyio
async def test_unhandled_exception_uses_generic_stable_error_response():
    from httpx import ASGITransport, AsyncClient

    from ecom_be.main import create_app

    application = create_app()

    async def failing_route():
        raise RuntimeError("password=do-not-expose")

    application.add_api_route("/test-failure", failing_route, methods=["GET"])
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test-failure")

    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_server_error",
        "message": "Internal server error",
    }
    assert "do-not-expose" not in response.text


def test_structured_logging_redacts_sensitive_values():
    from ecom_be.core.logging import StructuredJsonFormatter

    secrets = {
        "authorization": "auth-secret",
        "cookie": "cookie-secret",
        "connection": "db-secret",
        "password": "plain-password",
        "token": "token-secret",
    }
    connection_string = "db://" + f"user:{secrets['connection']}@db.example/resource"
    record = logging.makeLogRecord(
        {
            "name": "test.logger",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "authorization=%s cookie=%s token=%s",
            "args": (
                f"Bearer {secrets['authorization']}",
                f"session={secrets['cookie']}",
                secrets["token"],
            ),
            "headers": {
                "Authorization": f"Bearer {secrets['authorization']}",
                "Cookie": f"session={secrets['cookie']}",
            },
            "connection_string": connection_string,
            "password": secrets["password"],
            "access_token": secrets["token"],
            "safe_field": "safe-value",
        }
    )

    output = StructuredJsonFormatter().format(record)
    payload = json.loads(output)

    assert isinstance(payload, dict)
    assert payload["safe_field"] == "safe-value"
    assert all(secret not in output for secret in secrets.values())


def test_redacting_filter_handles_sensitive_format_arguments():
    from ecom_be.core.logging import RedactingFilter, StructuredJsonFormatter

    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token=%s connection_string=%s authorization %s cookie %s",
        args=(
            "token-secret",
            "db-secret",
            "auth-secret",
            "session=cookie-secret",
        ),
        exc_info=None,
    )

    RedactingFilter().filter(record)
    output = StructuredJsonFormatter().format(record)

    assert "token-secret" not in output
    assert "db-secret" not in output
    assert "auth-secret" not in output
    assert "cookie-secret" not in output


def test_redacting_filter_handles_generic_credential_url():
    from ecom_be.core.logging import RedactingFilter, StructuredJsonFormatter

    credential_url = "db:" + "//user:" + "connection-secret@db.example/resource"
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="connecting to %s",
        args=(credential_url,),
        exc_info=None,
    )

    RedactingFilter().filter(record)
    output = StructuredJsonFormatter().format(record)

    assert "connection-secret" not in output


def test_create_app_configures_json_logging():
    from ecom_be.core.logging import StructuredJsonFormatter
    from ecom_be.main import create_app

    create_app()

    assert any(
        isinstance(handler.formatter, StructuredJsonFormatter)
        for handler in logging.getLogger().handlers
    )


@pytest.mark.anyio
async def test_cors_uses_validated_origin_and_allows_credentials():
    from fastapi.middleware.cors import CORSMiddleware
    from httpx import ASGITransport, AsyncClient
    from pydantic import PostgresDsn, RedisDsn

    from ecom_be.core.config import Settings
    from ecom_be.main import create_app

    settings = Settings(
        database_url=PostgresDsn.build(
            scheme="postgresql+asyncpg",
            host="localhost",
            port=5432,
            path="ecommerce",
        ),
        redis_url=RedisDsn.build(scheme="redis", host="localhost", port=6379, path="0"),
        cors_origins=("http://localhost:3000",),
    )
    application = create_app(settings)
    transport = ASGITransport(app=application)
    cors_middleware = next(
        middleware
        for middleware in application.user_middleware
        if middleware.cls is CORSMiddleware
    )
    assert cors_middleware.kwargs["allow_origins"] == ["http://localhost:3000"]
    assert cors_middleware.kwargs["allow_origins"] != ["*"]
    assert cors_middleware.kwargs["allow_credentials"] is True
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/health/live",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"
