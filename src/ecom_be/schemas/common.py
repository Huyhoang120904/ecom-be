"""The one response envelope, owned by the router layer.

Every ``2xx`` body with a JSON payload is a ``BaseResponse``: ``data`` carries the
payload and ``status_code`` / ``message`` carry the outcome, so a client reads the
result from the body it already has rather than inferring it from the HTTP status
alone.

``data`` is never ``None`` — an empty collection is ``{"data": []}`` — so a client can
unwrap unconditionally.

Errors are deliberately not enveloped. They keep the stable ``{"error", "message"}``
shape from ``core/errors.py``, and ``error`` being present is what distinguishes a
failure from a success.

Two things are load-bearing about how this is declared:

* It is a plain generic and is used *directly* as ``response_model=BaseResponse[X]``.
  The per-endpoint ``XEnvelope`` subclasses this replaces existed only to keep the
  generic's type-variable name out of the published schema names. That cost a class
  per endpoint and a parallel naming convention in the frontend's generated types;
  the trade is documented in ``tests/unit/test_openapi_envelope.py``.
* ``message`` is bounded because the published OpenAPI document is the contract and
  ``tests/unit/test_openapi_string_limits.py`` fails on any unbounded string it finds.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

# Every success message is short by nature; the bound exists so the contract carries
# a maximum rather than leaving a client to guess one.
MESSAGE_MAX = 256

DataT = TypeVar("DataT")


class BaseResponse(BaseModel, Generic[DataT]):
    """The envelope every success body is wrapped in."""

    status_code: int = Field(description="The HTTP status code, echoed in the body")
    message: str = Field(
        default="Success",
        max_length=MESSAGE_MAX,
        description="A short human-readable summary of the outcome",
    )
    data: DataT
