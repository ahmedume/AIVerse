# src/app/schemas/plagiarism_schema.py
# Purpose: plagiarism request/response payloads.
# Exports: PlagiarismSource, PlagiarismRequest

from pydantic import BaseModel

from app.schemas.detect_schema import DetectSource


class PlagiarismRequest(BaseModel):
    source: DetectSource
    max_results: int = 5  # matched URLs to include per fragment (1-20)


class PlagiarismSource(BaseModel):
    pass