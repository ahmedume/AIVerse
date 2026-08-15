# src/app/services/auth_service.py
# Purpose: register/login/refresh/me orchestration; all auth errors are generic
#          to prevent user enumeration; nothing sensitive ever leaves this module.
# Exports: register, authenticate, build_me_payload

import structlog
from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthorizationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    set_auth_cookies,
    verify_password_or_dummy,
    verify_token,
)
from app.repositories import user_repo
from app.schemas.user_schema import LoginIn, MeOut, RegisterIn, SettingsOut, UserOut

settings = get_settings()
logger = structlog.get_logger()

_INVALID_CREDENTIALS = AuthorizationError("Invalid email or password", "INVALID_CREDENTIALS")


async def register(session: AsyncSession, payload: RegisterIn, response: Response) -> UserOut:
    existing = await user_repo.get_by_email(session, payload.email)
    if existing:
        raise ConflictError("An account with this email already exists", "EMAIL_TAKEN")

    first_user = await user_repo.count_users(session) == 0
    role = "admin" if first_user else "user"

    user = await user_repo.create(
        session,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=role,
        name=payload.name,
    )
    await session.commit()
    await session.refresh(user)

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    set_auth_cookies(response, access, refresh)

    logger.info("auth.register", user_id=user.id, first_user=first_user)
    return UserOut.model_validate(user)


async def authenticate(session: AsyncSession, payload: LoginIn, response: Response) -> UserOut:
    user = await user_repo.get_by_email(session, payload.email)
    if user is None or not verify_password_or_dummy(payload.password,
                                                    user.password_hash if user else None):
        # generic + time-equalized: identical for unknown email and bad password
        raise _INVALID_CREDENTIALS
    if not user.is_active:
        raise _INVALID_CREDENTIALS

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    set_auth_cookies(response, access, refresh)

    logger.info("auth.login", user_id=user.id)
    return UserOut.model_validate(user)


async def refresh(session: AsyncSession, refresh_cookie: str, response: Response) -> UserOut:
    user_id = verify_token(refresh_cookie, "refresh", "INVALID_REFRESH_TOKEN")
    user = await user_repo.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise AuthorizationError("Account no longer active", "INVALID_REFRESH_TOKEN")

    set_auth_cookies(response, create_access_token(user.id), create_refresh_token(user.id))
    logger.info("auth.refresh", user_id=user.id)
    return UserOut.model_validate(user)


async def build_me_payload(session: AsyncSession, user_id: str) -> MeOut:
    user = await user_repo.get_by_id(session, user_id)
    if user is None:
        raise AuthorizationError("Account not found", "UNAUTHORIZED")
    user_settings = await user_repo.ensure_settings(session, user_id)
    await session.commit()
    return MeOut(
        user=UserOut.model_validate(user),
        settings=SettingsOut.model_validate(user_settings),
        providers=settings.configured_providers(),
    )