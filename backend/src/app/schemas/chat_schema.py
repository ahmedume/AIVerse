# src/app/schemas/chat_schema.py
# Purpose: RAG chat request payloads.
# Exports: ChatRequest

from pydantic import BaseModel

from app.schemas.detect_schema import DetectSource


class ChatRequest(BaseModel):
    source: DetectSource
    question: str = "Where is the most AI content in this document, and what should I change?"