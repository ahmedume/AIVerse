# src/app/schemas/humanize_schema.py
# Purpose: humanizer request/response payloads.
# Exports: HumanizeRequest

from pydantic import BaseModel, Field

from app.schemas.detect_schema import DetectSource


class HumanizeRequest(BaseModel):
    source: DetectSource
    level: int = Field(
        ge=1, le=7, description="1-2 aggressive humanizing, 3-5 balanced, 6-7 corporate"
    )