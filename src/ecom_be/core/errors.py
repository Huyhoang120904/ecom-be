import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


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
    """Register the application's stable error response handlers."""

    application.add_exception_handler(
        RequestValidationError, request_validation_exception_handler
    )
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(Exception, internal_server_error_handler)
