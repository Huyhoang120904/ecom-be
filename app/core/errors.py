import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """A domain failure with a fixed, safe client-facing representation.

    The status code and the stable ``code`` live on the class, so a service
    describes what went wrong without knowing anything about HTTP, and
    ``core.errors`` renders every domain failure in one place.

    ``message`` is a class constant and is never assembled from request data: a
    message built from input is reflection under a different name, and returning
    exception detail to a client is forbidden.

    Subclasses live in the module that owns the meaning, because ``core`` must not
    import a feature module. ``errors/identity.py`` is the reference.
    """

    code: str = "internal_server_error"
    status_code: int = 500
    message: str = "Internal server error"


_HTTP_ERROR_MESSAGES: dict[int, tuple[str, str]] = {
    400: ("bad_request", "Bad request"),
    401: ("unauthorized", "Authentication required"),
    403: ("forbidden", "Forbidden"),
    404: ("not_found", "Resource not found"),
    405: ("method_not_allowed", "Method not allowed"),
    409: ("conflict", "Conflict"),
    422: ("unprocessable_entity", "Request could not be processed"),
    429: ("too_many_requests", "Too many requests"),
    500: ("internal_server_error", "Internal server error"),
    502: ("bad_gateway", "Bad gateway"),
    503: ("service_unavailable", "Service unavailable"),
    504: ("gateway_timeout", "Gateway timeout"),
}


def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render a domain error with the same body shape as every other failure."""

    del request
    if not isinstance(exc, AppError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


def http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return a stable, safe response for an HTTP exception."""

    del request
    status_code = exc.status_code if isinstance(exc, StarletteHTTPException) else 500
    error, message = _HTTP_ERROR_MESSAGES.get(
        status_code,
        ("http_error", "Request failed"),
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "message": message},
        headers=getattr(exc, "headers", None),
    )


def request_validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return a stable, safe response for invalid request data."""

    del request, exc
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
        },
    )


def internal_server_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return a generic response without exposing internal exception details."""

    del request, exc
    logger.error("Unhandled application exception")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "Internal server error",
        },
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Register the application's stable error response handlers.

    Every failure the API can produce, whether raised by a service or by the
    framework, is rendered as ``{"error": <code>, "message": <text>}``. That single
    shape is what lets a client handle errors without inspecting stack traces or
    string matching.
    """

    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(
        RequestValidationError, request_validation_exception_handler
    )
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(Exception, internal_server_error_handler)
