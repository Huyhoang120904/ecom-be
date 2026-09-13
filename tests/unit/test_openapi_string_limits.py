"""Contract: every string in the published API declares a maximum length.

An unbounded string field is a bound that exists nowhere. It cannot be enforced at
the schema layer, it cannot be a database ``CHECK``, and the only place it surfaces
is as a truncated value or a swallowed error somewhere downstream.

This gate walks the generated OpenAPI document rather than the source, because the
document is what frontends generate from and it is the contract that actually
ships. A property is exempt when it is bounded some other way the document can
express:

* ``format``: ``uuid``, ``date-time``, ``email`` and friends have their own grammar.
* ``enum``: a closed set of values, each one already written down.
* ``const``: exactly one possible value. Pydantic renders a single-value
  ``Literal["ok"]`` as ``const`` rather than ``enum``, and bounding a one-value
  string further would be meaningless.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from ecom_be.main import app

# FastAPI generates these two to document its own ``RequestValidationError``
# response. This application replaces that response body with the stable
# ``{"error", "message"}`` shape in ``core/errors.py``, so neither schema is part
# of the contract and neither should be held to it.
FRAMEWORK_SCHEMAS = frozenset({"HTTPValidationError", "ValidationError"})

# A property carrying any of these is bounded by something other than maxLength.
BOUNDED_OTHERWISE = ("format", "enum", "const")


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return app.openapi()


def _iter_subschemas(
    schema: Any,
    document: dict[str, Any],
    path: tuple[str, ...] = (),
    refs_in_path: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
    """Yield ``(property path, subschema)`` for a schema and everything it reaches.

    ``$ref`` is followed, with the reference chain tracked so a self-referential
    model terminates instead of recursing forever. The chain is per-path rather
    than global: a component referenced from two places is still visited twice, so
    a shared model cannot hide an unbounded field after its first visit.
    """

    if not isinstance(schema, dict):
        return

    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        if name in refs_in_path:
            return
        target = document.get("components", {}).get("schemas", {}).get(name, {})
        yield from _iter_subschemas(target, document, path, (*refs_in_path, name))
        return

    yield path, schema

    for keyword in ("allOf", "oneOf", "anyOf"):
        for part in schema.get(keyword) or []:
            yield from _iter_subschemas(part, document, path, refs_in_path)

    items = schema.get("items")
    if isinstance(items, dict):
        yield from _iter_subschemas(items, document, (*path, "[]"), refs_in_path)

    for prop_name, prop in (schema.get("properties") or {}).items():
        yield from _iter_subschemas(prop, document, (*path, prop_name), refs_in_path)


def _unbounded_string_properties(document: dict[str, Any]) -> list[str]:
    schemas = document.get("components", {}).get("schemas", {})
    unbounded: list[str] = []

    for schema_name, schema in sorted(schemas.items()):
        if schema_name in FRAMEWORK_SCHEMAS:
            continue
        for path, subschema in _iter_subschemas(schema, document):
            if subschema.get("type") != "string":
                continue
            if any(keyword in subschema for keyword in BOUNDED_OTHERWISE):
                continue
            if "maxLength" in subschema:
                continue
            label = ".".join((schema_name, *path)) if path else schema_name
            unbounded.append(label)

    return sorted(set(unbounded))


def test_every_string_property_declares_a_maximum_length(document):
    unbounded = _unbounded_string_properties(document)

    assert unbounded == [], (
        "These response or request string properties declare no maxLength: "
        f"{unbounded}. Bound each one (a Field(max_length=...) on the schema) or, "
        "if it is genuinely bounded another way, constrain it with a format or an "
        "enum so this gate can see the bound."
    )


def test_the_gate_would_catch_an_unbounded_field(document):
    """The gate must fail on a violation, not merely pass on a clean document."""

    poisoned = {
        "components": {
            "schemas": {
                **document["components"]["schemas"],
                "ProbeUnbounded": {
                    "type": "object",
                    "properties": {"nickname": {"type": "string"}},
                },
            }
        }
    }

    unbounded = _unbounded_string_properties(poisoned)

    assert "ProbeUnbounded.nickname" in unbounded


def test_a_referenced_component_is_checked_through_its_reference(document):
    """A shared model must not escape the gate by being referenced, not inlined."""

    poisoned = {
        "components": {
            "schemas": {
                "ProbeShared": {
                    "type": "object",
                    "properties": {"note": {"type": "string"}},
                },
                "ProbeHolder": {
                    "type": "object",
                    "properties": {
                        "shared": {"$ref": "#/components/schemas/ProbeShared"},
                    },
                },
            }
        }
    }

    unbounded = _unbounded_string_properties(poisoned)

    assert "ProbeHolder.shared.note" in unbounded
