"""Contract: every 2xx response with a body is wrapped in ``BaseResponse``.

The frontend unwraps one envelope shape in one place. An endpoint that returns a
bare payload would break that contract silently: the unwrap would fail at runtime
rather than at compile time, and only for the screens that call it.

This gate reads the published OpenAPI document. A ``204`` has no body and is
exempt. Errors are deliberately not enveloped: they keep the ``{"error",
"message"}`` shape, and ``error`` being present is the discriminator, so
non-2xx responses are exempt here.
"""

from __future__ import annotations

from typing import Any

import pytest

from ecom_be.main import app

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
ENVELOPE_SUFFIX = "Envelope"

# These responses carry a binary body, not JSON, so there is nothing to wrap. They
# are listed by path rather than matched by a rule, because "this endpoint streams
# bytes" is a property of the endpoint and not a pattern worth inferring.
BINARY_PATHS = frozenset(
    {
        "/api/v1/media/avatar/{user_id}.webp",
        "/api/v1/media/shop-background/{shop_id}.webp",
    }
)


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return app.openapi()


def _bodyful_2xx_responses(document: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """Every 2xx response that declares a JSON body, with its schema reference."""

    found: list[tuple[str, str, Any]] = []
    for path, operations in sorted(document.get("paths", {}).items()):
        if path in BINARY_PATHS:
            continue
        for method, operation in operations.items():
            if method not in METHODS or not isinstance(operation, dict):
                continue
            for status_code, response in sorted(operation.get("responses", {}).items()):
                if not status_code.startswith("2") or status_code == "204":
                    continue
                schema = (
                    (response.get("content") or {})
                    .get("application/json", {})
                    .get("schema")
                )
                found.append((f"{method.upper()} {path}", status_code, schema))
    return found


def test_the_document_publishes_at_least_one_enveloped_endpoint(document):
    """Guards against the gate passing because it found nothing to check."""

    assert _bodyful_2xx_responses(document), (
        "no 2xx JSON responses were found; the gate is not inspecting the document"
    )


def test_every_2xx_json_response_is_enveloped(document):
    offenders: list[str] = []

    for route, status_code, schema in _bodyful_2xx_responses(document):
        if not isinstance(schema, dict) or "$ref" not in schema:
            offenders.append(
                f"{route} {status_code}: schema is {schema!r}, not a reference"
            )
            continue
        name = schema["$ref"].rsplit("/", 1)[-1]
        if not name.endswith(ENVELOPE_SUFFIX):
            offenders.append(f"{route} {status_code}: {name} is not an envelope")

    assert offenders == [], (
        "These 2xx responses are not wrapped in a BaseResponse subclass: "
        f"{offenders}. Declare a concrete subclass (for example class "
        "SessionEnvelope(BaseResponse[SessionData])) and set it as response_model."
    )


def test_the_gate_would_catch_an_unenveloped_response(document):
    """The gate must fail on a violation, not merely pass on a clean document."""

    poisoned = {
        "paths": {
            "/probe": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ProbeBare"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    found = _bodyful_2xx_responses(poisoned)
    assert found == [
        (
            "GET /probe",
            "200",
            {"$ref": "#/components/schemas/ProbeBare"},
        )
    ]
    name = found[0][2]["$ref"].rsplit("/", 1)[-1]
    assert not name.endswith(ENVELOPE_SUFFIX), (
        "a bare payload must not satisfy the gate"
    )


def test_204_responses_are_not_required_to_carry_an_envelope(document):
    """A bodyless response has nothing to wrap."""

    found = _bodyful_2xx_responses(
        {
            "paths": {
                "/probe": {"delete": {"responses": {"204": {"description": "gone"}}}}
            }
        }
    )

    assert found == []
