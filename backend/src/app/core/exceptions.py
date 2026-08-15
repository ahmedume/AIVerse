# src/app/core/exceptions.py
# Purpose: typed application error hierarchy + FastAPI handlers mapping to
#          the unified { success, error: { code, message } } envelope.
# Exports: AppError, NotFoundError, ValidationError, AuthorizationError,
#          ForbiddenError, ProviderNotConfiguredError, register_exception_handlers

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app")


class AppError(Exception):
    """Base application error carrying an API error code."""

    def __init__(self, message: str, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, "NOT_FOUND")


class ValidationError(AppError):
    def __init__(self, message: str = "Invalid input", code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message, code)


class AuthorizationError(AppError):
    def __init__(self, message: str = "Unauthorized", code: str = "UNAUTHORIZED") -> None:
        super().__init__(message, code)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, "FORBIDDEN")


class ConflictError(AppError):
    def __init__(self, message: str = "Resource already exists", code: str = "CONFLICT") -> None:
        super().__init__(message, code)


class ProviderNotConfiguredError(AppError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Provider '{provider}' is not configured. Add its API key to .env.",
            "PROVIDER_NOT_CONFIGURED",
        )


_STATUS_MAP: dict[type[AppError], int] = {
    NotFoundError: 404,
    ValidationError: 422,
    AuthorizationError: 401,
    ForbiddenError: 403,
    ConflictError: 409,
    ProviderNotConfiguredError: 503,
}


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        status = _STATUS_MAP.get(type(exc), 400)
        return _error_response(status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = "; ".join(
            f"{'.'.join(str(loc) for loc in err.get('loc', []))}: {err.get('msg', '')}"
            for err in exc.errors()
        )
        return _error_response(422, "VALIDATION_ERROR", f"Validation failed: {details}")

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error_response(500, "INTERNAL_ERROR", "Something went wrong. Try again.")