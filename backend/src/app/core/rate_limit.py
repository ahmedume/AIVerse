# src/app/core/rate_limit.py
# Purpose: shared slowapi limiter + per-user key helper used by all routers.
# Exports: limiter, user_key

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])


def user_key(request: Request) -> str:
    user_id = getattr(request.state, "current_user_id", None)
    return f"user:{user_id}" if user_id else get_remote_address(request)