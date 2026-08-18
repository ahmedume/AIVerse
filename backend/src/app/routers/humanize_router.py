# src/app/routers/humanize_router.py
# Purpose: SSE endpoint for 1-7 humanization rewrites.
# Exports: router

from fastapi import APIRouter

router = APIRouter(prefix="", tags=["humanize"])