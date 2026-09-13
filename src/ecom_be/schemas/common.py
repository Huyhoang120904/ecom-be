"""Transport shapes shared by every module.

``AGENTS.md`` bans a global catch-all schema file, and that rule is about
capability boundaries: ``LoginRequest`` belongs to the identity module, and a
shared ``schemas.py`` holding it would be exactly the boundary leak the rule
forbids. A generic response envelope has no capability and every module needs it,
so it belongs here with the other cross-module HTTP wiring (``deps.py``,
``router.py``).

Every endpoint declares a concrete subclass, never a bare ``BaseResponse[Thing]``.
A bare generic works at runtime, but it makes OpenAPI name the schema
``BaseResponse_Thing_``, which leaks the type-variable name into every generated
client type.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class BaseResponse(BaseModel, Generic[DataT]):
    """The envelope every success body is wrapped in.

    The field is named ``data`` and it is never ``None``: an empty collection is
    ``{"data": []}``, never ``{"data": null}``, so a client can unwrap
    unconditionally.

    Errors are deliberately not enveloped. They keep the stable
    ``{"error", "message"}`` shape from ``core/errors.py``, and ``error`` being
    present is what distinguishes a failure from a success.
    """

    data: DataT
