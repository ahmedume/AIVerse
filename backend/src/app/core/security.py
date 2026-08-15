# src/app/core/security.py
# Purpose: passwords, JWTs, and httpOnly cookie handling.
# Exports: hash_password, verify_password, create_access_token, create_refresh_token,
#          verify_token, set_auth_cookies, clear_auth_cookies

import math
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from fastapi import Response
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from app.core.config import get_settings
from app.core.exceptions import AuthorizationError

settings = get_settings()
logger = structlog.get_logger()

_pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12, deprecated="auto")

# Precomputed dummy hash so "unknown user" logins cost the same as real bcrypt
# verification (~300 ms) — defeats timing-based user enumeration.
_DUMMY_HASH = _pwd_context.hash("dummy-password-for-timing-equalization")

_TOKEN_TYPE_CLAIM = "typ"
_ISSUER_CLAIM = "iss"
_SUBJECT_CLAIM = "sub"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return _pwd_context.verify(password, password_hash)
    except (ValueError, UnknownHashError):
        return False


def verify_password_or_dummy(password: str, password_hash: str | None) -> bool:
    """Verify against the stored hash, or against a dummy hash when the user
    does not exist — both paths take ~equal time."""
    if password_hash:
        return verify_password(password, password_hash)
    return verify_password(password, _DUMMY_HASH)


def _token_expiry(minutes: int) -> int:
    return math.floor(datetime.now(UTC).timestamp()) + minutes * 60


def _encode(claims: dict[str, Any], expires_in_minutes: int) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        **claims,
        "jti": uuid4().hex,  # unique per token: rotation always produces a new value
        "iat": math.floor(now.timestamp()),
        "exp": _token_expiry(expires_in_minutes),
        _ISSUER_CLAIM: settings.JWT_ISSUER,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _encode({_SUBJECT_CLAIM: user_id, _TOKEN_TYPE_CLAIM: "access"},
                   settings.ACCESS_TOKEN_EXPIRE_MINUTES)


def create_refresh_token(user_id: str) -> str:
    return _encode({_SUBJECT_CLAIM: user_id, _TOKEN_TYPE_CLAIM: "refresh"},
                   settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60)


def verify_token(token: str, expected_type: str, error_code: str) -> str:
    """Verify signature + expiry + issuer + token type; returns the subject (user id)."""
    try:
        claims = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            options={"require_exp": True, "verify_iat": True},
        )
    except JWTError as exc:
        logger.info("auth.token_invalid", reason=str(exc))
        raise AuthorizationError("Invalid or expired token", error_code) from exc
    if claims.get(_TOKEN_TYPE_CLAIM) != expected_type:
        raise AuthorizationError("Invalid token type", error_code)
    subject = claims.get(_SUBJECT_CLAIM)
    if not isinstance(subject, str) or not subject:
        raise AuthorizationError("Invalid token subject", error_code)
    return subject


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        settings.COOKIE_NAME_ACCESS,
        access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    response.set_cookie(
        settings.COOKIE_NAME_REFRESH,
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    for name in (settings.COOKIE_NAME_ACCESS, settings.COOKIE_NAME_REFRESH):
        response.delete_cookie(name, path="/", samesite="lax", secure=settings.cookie_secure)