# src/app/schemas/export_schema.py
# Purpose: export request payloads.
# Exports: ExportRequest

from pydantic import BaseModel

from app.schemas.detect_schema import DetectSource


class ExportRequest(BaseModel):
    source: DetectSource
    format: str  # docx | pdf