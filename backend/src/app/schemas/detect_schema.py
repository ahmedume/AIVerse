# src/app/schemas/detect_schema.py
# Purpose: detection request/response payloads.
# Exports: DetectSource, DetectRequest

from pydantic import BaseModel


class DetectSource(BaseModel):
    file_id: str | None = None
    text: str | None = None


class DetectRequest(BaseModel):
    source: DetectSource