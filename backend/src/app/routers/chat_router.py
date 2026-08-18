# src/app/routers/chat_router.py
# Purpose: SSE endpoint for the RAG chatbot (AI-locator).
# Exports: router

from fastapi import APIRouter

router = APIRouter(prefix="", tags=["chat"])