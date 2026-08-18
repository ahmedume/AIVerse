# src/app/services/detect_service.py
# Purpose: per-paragraph AI% — 0.6 LLM + 0.4 heuristic blend, streamed as SSE.
# Exports: detect_stream

import asyncio
import re
from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage

from app.core.blocks import Block
from app.core.config import get_settings
from app.core.heuristics import heuristic_score
from app.core.llm import get_model_chain
from app.core.sse import sse
from app.services import parse_service

settings = get_settings()
_LIMIT = asyncio.Semaphore(3)
_FLAGGED_AT = 70
_BLEND = 0.6
_SCORE_RE = re.compile(r"\"?score\"?\s*[:=]\s*(\d{1,3})", re.IGNORECASE)
_REASON_RE = re.compile(r"\"reason\"\s*:\s*\"([^\"]{1,120})\"")

_PROMPT = """Rate how likely this text was written by an AI, 0-100.
Reply with JSON only: {{"score": <int 0-100>, "reason": "<phrase, max 10 words>"}}

TEXT:
{text}"""


def _parse_llm_score(raw: str) -> tuple[float, str] | None:
    match = _SCORE_RE.search(raw)
    if not match:
        return None
    score = min(100.0, float(match.group(1)))
    reason_match = _REASON_RE.search(raw)
    return score, reason_match.group(1) if reason_match else "LLM assessment"


def _llm_score(text: str) -> tuple[float, str] | None:
    chain = get_model_chain(settings.DEFAULT_PROVIDER, settings.DEFAULT_MODEL, temperature=0.2)
    for model in chain:
        try:
            response = model.invoke([HumanMessage(content=_PROMPT.format(text=text[:3000]))])
            return _parse_llm_score(str(response.content))
        except Exception:
            continue
    return None


def _score_block(block, heuristic: float) -> dict:
    llm = _llm_score(block.text)
    if llm:
        score, reason = llm
        blended = round(_BLEND * score + (1 - _BLEND) * heuristic, 1)
        return {
            "index": block.index,
            "ai_score": blended,
            "reason": f"{reason} · heuristic {round(heuristic)}",
        }
    return {
        "index": block.index,
        "ai_score": heuristic,
        "reason": "Statistical heuristic only (LLM unavailable)",
    }


async def _score_worker(block, heuristic: float) -> dict:
    async with _LIMIT:
        return await asyncio.to_thread(_score_block, block, heuristic)


async def detect_stream(blocks: list[Block]) -> AsyncIterator[str]:
    scorable = [b for b in blocks if b.type in ("paragraph", "list_item", "blockquote")]
    yield sse({"event": "meta", "data": {"total": len(scorable), "flagged_threshold": _FLAGGED_AT}})
    if not scorable:
        yield sse({"event": "done", "data": {"overall": 0.0, "flagged": False, "scores": []}})
        return

    results = await asyncio.gather(
        *[_score_worker(b, heuristic_score(b.text)) for b in scorable]
    )
    for block, result in zip(scorable, results):
        block.ai_score = result["ai_score"]
        block.reason = result["reason"]
        yield sse({"event": "block_score", "data": result})

    overall = round(sum(r["ai_score"] for r in results) / len(results), 1)
    yield sse(
        {
            "event": "done",
            "data": {
                "overall": overall,
                "flagged": overall >= _FLAGGED_AT,
                "scores": [{"index": r["index"], "ai_score": r["ai_score"]} for r in results],
            },
        }
    )
