# src/app/main.py
# Purpose: FastAPI application factory — CORS, security headers, request logging,
#          exception handlers, routers, lifespan.
# Exports: app

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers

settings = get_settings()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.vectorstore_dir.mkdir(parents=True, exist_ok=True)
    logger.info("aiverse api starting", env=settings.APP_ENV)
    yield
    logger.info("aiverse api stopped")


class SecurityHeadersMiddleware:
    """Pure ASGI middleware: harden response headers without buffering bodies
    (a plain ASGI wrapper is safe for SSE streaming)."""

    _HEADERS = (
        (b"X-Content-Type-Options", b"nosniff"),
        (b"X-Frame-Options", b"DENY"),
        (b"Referrer-Policy", b"strict-origin-when-cross-origin"),
        (b"Permissions-Policy", b"geolocation=(), microphone=(), camera=()"),
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if settings.is_production:
                    headers.append(
                        (b"Strict-Transport-Security", b"max-age=31536000; includeSubDomains")
                    )
                message = {**message, "headers": headers + list(self._HEADERS)}
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RequestLoggingMiddleware:
    """Pure ASGI middleware: structlog access log for HTTP requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                logger.info(
                    "http.request",
                    method=scope.get("method"),
                    path=scope.get("path"),
                    status=message["status"],
                    duration_ms=round((perf_counter() - start) * 1000, 1),
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


def create_app() -> FastAPI:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    app = FastAPI(title="AIverse API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)

    from app.routers import (
        chat_router,
        detect_router,
        export_router,
        files_router,
        health_router,
        humanize_router,
        plagiarism_router,
    )

    app.include_router(health_router.router)
    app.include_router(files_router.router)
    app.include_router(detect_router.router)
    app.include_router(plagiarism_router.router)
    app.include_router(humanize_router.router)
    app.include_router(export_router.router)
    app.include_router(chat_router.router)
    return app


app = create_app()
