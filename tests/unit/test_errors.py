"""Contract: a domain error carries its own transport representation.

Services describe a failure by raising a typed error. The status code and the
stable client-facing ``code`` live on the class, so a service never selects an
HTTP status and ``core`` never learns a module's vocabulary.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.errors import AppError, register_exception_handlers


class ProbeTeapot(AppError):
    code = "probe_teapot"
    status_code = 418
    message = "I am a teapot"


class ProbeUnreadable(AppError):
    """A subclass that overrides nothing keeps the base defaults."""


@pytest.fixture
def teapot_app() -> FastAPI:
    application = FastAPI()
    register_exception_handlers(application)

    @application.get("/teapot")
    async def teapot() -> None:
        raise ProbeTeapot

    @application.get("/unreadable")
    async def unreadable() -> None:
        raise ProbeUnreadable

    @application.get("/framework")
    async def framework() -> None:
        raise HTTPException(status_code=403, detail="token=do-not-expose")

    return application


def test_app_error_defaults_are_safe():
    error = ProbeUnreadable()

    assert error.status_code == 500
    assert error.code == "internal_server_error"
    assert error.message == "Internal server error"


def test_app_error_is_an_exception():
    with pytest.raises(ProbeTeapot):
        raise ProbeTeapot


@pytest.mark.anyio
async def test_a_domain_error_renders_its_code_and_message(teapot_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=teapot_app), base_url="http://test"
    ) as client:
        response = await client.get("/teapot")

    assert response.status_code == 418
    assert response.json() == {"error": "probe_teapot", "message": "I am a teapot"}


@pytest.mark.anyio
async def test_a_subclass_without_overrides_is_a_generic_500(teapot_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=teapot_app), base_url="http://test"
    ) as client:
        response = await client.get("/unreadable")

    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_server_error",
        "message": "Internal server error",
    }


@pytest.mark.anyio
async def test_the_domain_error_shape_matches_the_framework_error_shape(
    teapot_app: FastAPI,
):
    """One body shape for every failure, whichever layer raised it."""

    async with AsyncClient(
        transport=ASGITransport(app=teapot_app), base_url="http://test"
    ) as client:
        domain = await client.get("/teapot")
        framework = await client.get("/framework")

    assert set(domain.json()) == {"error", "message"}
    assert set(framework.json()) == {"error", "message"}
    assert "do-not-expose" not in framework.text


def test_the_message_is_a_class_constant_not_instance_data():
    """A message assembled from request data would reintroduce reflection.

    ``AGENTS.md`` forbids returning exception detail to a client, so the rendered
    message must come from the class and never from the raise site.
    """

    assert isinstance(ProbeTeapot.message, str)
    assert isinstance(ProbeTeapot.code, str)
    assert isinstance(ProbeTeapot.status_code, int)

    # An exception may carry whatever the raise site passes, and none of it reaches
    # the response: the handler reads the class attributes only.
    with pytest.raises(ProbeTeapot):
        raise ProbeTeapot("password=hunter2")

    assert ProbeTeapot.status_code == 418
    assert ProbeTeapot.message == "I am a teapot"
    assert "hunter2" not in ProbeTeapot.message
