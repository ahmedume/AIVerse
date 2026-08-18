# src/app/routers/detect_router.py
# Purpose: SSE endpoint for per-paragraph AI-content detection.
# Exports: router

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.detect_schema import DetectRequest
from app.services import detect_service, parse_service

router = APIRouter(prefix="/api", tags=["detect"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/detect")
async def detect(request: DetectRequest) -> StreamingResponse:
    _, blocks = parse_service.resolve_source(request.source.model_dump())
    return StreamingResponse(
        detect_service.detect_stream(blocks),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
