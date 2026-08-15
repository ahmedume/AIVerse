# src/app/schemas/common.py
# Purpose: unified { success, data } response envelope.
# Exports: Envelope

from pydantic import BaseModel


class Envelope[T](BaseModel):
    success: bool = True
    data: T | None = None