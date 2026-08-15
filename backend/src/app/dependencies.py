# src/app/dependencies.py
# Purpose: request-scoped auth dependencies for protected routes.
# Exports: get_current_user, require_admin

from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.database import SessionDep
from app.core.exceptions import AuthorizationError, ForbiddenError
from app.core.security import verify_token
from app.models.user_model import User
from app.repositories import user_repo

settings = get_settings()


async def get_current_user(request: Request, session: SessionDep) -> User:
    access_cookie = request.cookies.get(settings.COOKIE_NAME_ACCESS)
    if not access_cookie:
        raise AuthorizationError("Not authenticated", "UNAUTHORIZED")

    user_id = verify_token(access_cookie, "access", "UNAUTHORIZED")
    user = await user_repo.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise AuthorizationError("Account is not active", "UNAUTHORIZED")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise ForbiddenError("Admin access required")
    return current_user