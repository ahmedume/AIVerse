# src/app/routers/plagiarism_router.py
# Purpose: SSE endpoint for DuckDuckGo plagiarism scanning.
# Exports: router

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.plagiarism_schema import PlagiarismRequest
from app.services import parse_service, plagiarism_service

router = APIRouter(prefix="/api", tags=["plagiarism"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/plagiarism")
async def plagiarism(request: PlagiarismRequest) -> StreamingResponse:
    _, blocks = parse_service.resolve_source(request.source.model_dump())
    return StreamingResponse(
        plagiarism_service.plagiarism_stream(
            request.source.model_dump(), max_results=request.max_results
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )