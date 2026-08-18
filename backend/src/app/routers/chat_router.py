# src/app/routers/chat_router.py
# Purpose: SSE endpoint for the RAG chatbot agent.
# Exports: router

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.chat_schema import ChatRequest
from app.services import parse_service, rag_service

router = APIRouter(prefix="/api", tags=["chat"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    _, blocks = parse_service.resolve_source(request.source.model_dump())
    return StreamingResponse(
        rag_service.chat_stream(request.source.model_dump(), request.question),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )