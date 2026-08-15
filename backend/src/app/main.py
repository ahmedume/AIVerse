# src/app/main.py
# Purpose: FastAPI application factory — CORS, security headers, exception handlers,
#          slowapi rate limiting, routers, lifespan.
# Exports: app

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.routers.auth_router import limiter as auth_limiter
from app.routers.auth_router import router as auth_router
from app.routers.health_router import router as health_router

settings = get_settings()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    data_dir = settings.data_dir_path / "uploads"
    data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir_path / "vectorstore").mkdir(parents=True, exist_ok=True)
    logger.info("nexus api starting", env=settings.APP_ENV)
    yield
    logger.info("nexus api stopped")


class SecurityHeadersMiddleware:
    """Pure ASGI middleware: harden response headers without buffering bodies
    (a plain ASGI wrapper is safe for SSE streaming)."""

    _HEADERS = (
        (b"X-Content-Type-Options", b"nosniff"),
        (b"X-Frame-Options", b"DENY"),
        (b"Referrer-Policy", b"strict-origin-when-cross-origin"),
        (b"X-XSS-Protection", b"1; mode=block"),
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


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "error": {"code": "RATE_LIMITED", "message": "Too many requests. Wait and try again."},
        },
        headers={"Retry-After": "60"},
    )


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

    app = FastAPI(title="Nexus API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    app.state.limiter = auth_limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    return app


app = create_app()