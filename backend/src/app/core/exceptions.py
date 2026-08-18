# src/app/core/exceptions.py
# Purpose: typed application error hierarchy + FastAPI handlers mapping to
#          the unified { success, error: { code, message } } envelope.
# Exports: AppError, NotFoundError, ValidationError, ProviderNotConfiguredError,
#          register_exception_handlers

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


class ProviderNotConfiguredError(AppError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Provider '{provider}' is not configured. Add its API key to .env.",
            "PROVIDER_NOT_CONFIGURED",
        )


class FileTooLargeError(ValidationError):
    def __init__(self, limit_mb: int) -> None:
        super().__init__(f"File exceeds the {limit_mb} MB upload limit", "FILE_TOO_LARGE")


class UnsupportedFileTypeError(ValidationError):
    def __init__(self, ext: str, allowed: str) -> None:
        super().__init__(
            f"Unsupported file type '.{ext}'. Allowed: {allowed}.", "UNSUPPORTED_FILE_TYPE"
        )


class ParseFailedError(ValidationError):
    def __init__(self, message: str = "Could not parse the file") -> None:
        super().__init__(message, "PARSE_FAILED")


class EmptyDocumentError(ValidationError):
    def __init__(self) -> None:
        super().__init__("The document contains no readable text", "EMPTY_DOCUMENT")


_STATUS_MAP: list[tuple[type[AppError], int]] = [
    (FileTooLargeError, 413),
    (NotFoundError, 404),
    (ValidationError, 422),
    (ProviderNotConfiguredError, 503),
]


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        status = next((s for t, s in _STATUS_MAP if isinstance(exc, t)), 400)
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
