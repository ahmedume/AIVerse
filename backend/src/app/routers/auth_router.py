# src/app/routers/auth_router.py
# Purpose: public auth endpoints — register/login/refresh (rate-limited, cookies only).
# Exports: router

import structlog
from fastapi import APIRouter, Depends, Request, Response

from app.core.config import get_settings
from app.core.database import SessionDep
from app.core.exceptions import AuthorizationError
from app.core.rate_limit import limiter
from app.core.security import clear_auth_cookies
from app.dependencies import get_current_user
from app.models.user_model import User
from app.schemas.common import Envelope
from app.schemas.user_schema import LoginIn, MeOut, RegisterIn, UserOut
from app.services import auth_service

settings = get_settings()
logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=Envelope[UserOut])
@limiter.limit(settings.AUTH_RATE_LIMIT)
async def register(
    request: Request,
    payload: RegisterIn,
    response: Response,
    session: SessionDep,
) -> Envelope[UserOut]:
    user = await auth_service.register(session, payload, response)
    return Envelope(data=user)


@router.post("/login", response_model=Envelope[UserOut])
@limiter.limit(settings.AUTH_RATE_LIMIT)
async def login(
    request: Request,
    payload: LoginIn,
    response: Response,
    session: SessionDep,
) -> Envelope[UserOut]:
    user = await auth_service.authenticate(session, payload, response)
    return Envelope(data=user)


@router.post("/refresh", response_model=Envelope[UserOut])
@limiter.limit(settings.REFRESH_RATE_LIMIT)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
) -> Envelope[UserOut]:
    refresh_cookie = request.cookies.get(settings.COOKIE_NAME_REFRESH)
    if not refresh_cookie:
        raise AuthorizationError("Missing refresh token", "INVALID_REFRESH_TOKEN")
    user = await auth_service.refresh(session, refresh_cookie, response)
    return Envelope(data=user)


@router.post("/logout", response_model=Envelope[None])
async def logout(response: Response, _: SessionDep) -> Envelope[None]:
    clear_auth_cookies(response)
    logger.info("auth.logout")
    return Envelope(data=None)


@router.get("/me", response_model=Envelope[MeOut])
async def me(
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[MeOut]:
    payload = await auth_service.build_me_payload(session, current_user.id)
    return Envelope(data=payload)