# src/app/core/sse.py
# Purpose: SSE frame helper shared by every streaming router.
# Exports: sse

import json


def sse(payload: dict) -> str:
    """Serialize a dict as a single SSE data frame."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
