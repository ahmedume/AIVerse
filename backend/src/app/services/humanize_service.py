# src/app/services/humanize_service.py
# Purpose: rewrite content at humanize levels 1-7 with structure preservation,
#          streaming tokens per block as SSE. Headings and blockquotes are kept
#          verbatim; facts/numbers are protected by prompt contract.
# Exports: level_profile, humanize_stream

from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage

from app.core.blocks import Block
from app.core.config import get_settings
from app.core.llm import get_model_chain
from app.core.sse import sse
from app.services import parse_service

settings = get_settings()

_PROFILES = {
    "human": (
        "Rewrite with MAXIMUM humanization: casual tone, varied sentence lengths, "
        "contractions, natural rhythm, a few small imperfections. Keep every fact, "
        "number, name, and date exactly the same. No bullet-point feel."
    ),
    "balanced": (
        "Rewrite in a balanced professional style: natural but polished, varied "
        "sentence structure, some contractions, smooth flow. Keep every fact, "
        "number, name, and date exactly the same."
    ),
    "corporate": (
        "Rewrite in a refined corporate tone: formal, confident, precise, well "
        "structured. Keep every fact, number, name, and date exactly the same."
    ),
}

_PROMPT = """{profile}

TEXT TO REWRITE:
{text}

Rewritten text only, no quotes, no commentary:"""


def level_profile(level: int) -> tuple[str, float]:
    """Map 1-7 to (profile, temperature)."""
    if level <= 2:
        return _PROFILES["human"], 0.9
    if level <= 5:
        return _PROFILES["balanced"], 0.7
    return _PROFILES["corporate"], 0.4


def _prompt_for(text: str, level: int) -> str:
    profile, _ = level_profile(level)
    return _PROMPT.format(profile=profile, text=text)


def _rewritable(block: Block) -> bool:
    return block.type in ("paragraph", "list_item")


def _chunk_text(content) -> str:
    """Extract plain text from model chunks (strings or Gemini-style part lists)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(content)


async def _rewrite_block(chain: list, block: Block, level: int) -> AsyncIterator[str]:
    """Stream rewritten tokens from the first model that works; fall back to
    the original text only when every provider fails."""
    for model in chain:
        try:
            prompt = HumanMessage(content=_prompt_for(block.text, level))
            async for chunk in model.astream([prompt]):
                piece = _chunk_text(getattr(chunk, "content", "") or "")
                if piece:
                    yield piece
            return
        except Exception:
            continue
    yield block.text


async def humanize_stream(source: dict, level: int) -> AsyncIterator[str]:
    _, blocks = parse_service.resolve_source(source)
    targets = [b for b in blocks if _rewritable(b)]
    yield sse({"event": "meta", "data": {"total": len(targets), "level": level}})

    chain = get_model_chain(
        settings.DEFAULT_PROVIDER, settings.DEFAULT_MODEL, temperature=level_profile(level)[1]
    )

    rewritten: list[dict] = []
    for block in blocks:
        if not _rewritable(block):
            continue
        yield sse({"event": "block_start", "data": {"index": block.index, "type": block.type}})
        pieces: list[str] = []
        if not chain:
            pieces = [block.text]
        else:
            async for piece in _rewrite_block(chain, block, level):
                pieces.append(piece)
                yield sse({"event": "token", "data": {"index": block.index, "token": piece}})
        new_text = "".join(pieces).strip() or block.text
        yield sse({"event": "block_end", "data": {"index": block.index, "text": new_text}})
        rewritten.append({"index": block.index, "type": block.type, "text": new_text})

    yield sse(
        {
            "event": "done",
            "data": {"level": level, "rewritten": len(rewritten), "blocks": rewritten},
        }
    )