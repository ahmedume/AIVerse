# src/app/routers/health_router.py
# Purpose: liveness check.
# Exports: router

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"success": True, "data": {"status": "ok", "version": "0.1.0"}}
