# src/app/routers/health_router.py
# Purpose: liveness probe.
# Exports: router

from fastapi import APIRouter

router = APIRouter(tags=["health"])

APP_VERSION = "0.1.0"


@router.get("/health")
async def health() -> dict[str, object]:
    return {"success": True, "data": {"status": "ok", "version": APP_VERSION}}