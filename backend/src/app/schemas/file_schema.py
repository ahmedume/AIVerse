# src/app/schemas/file_schema.py
# Purpose: file metadata payloads.
# Exports: FileOut

from pydantic import BaseModel


class FileOut(BaseModel):
    id: str
    filename: str
    size: int
    blocks: int
    words: int
    created_at: float