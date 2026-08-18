# src/app/routers/humanize_router.py
# Purpose: SSE endpoint for level 1-7 humanizing.
# Exports: router

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.humanize_schema import HumanizeRequest
from app.services import humanize_service, parse_service

router = APIRouter(prefix="/api", tags=["humanize"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/humanize")
async def humanize(request: HumanizeRequest) -> StreamingResponse:
    _, blocks = parse_service.resolve_source(request.source.model_dump())
    return StreamingResponse(
        humanize_service.humanize_stream(request.source.model_dump(), request.level),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )