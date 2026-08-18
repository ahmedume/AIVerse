# src/app/core/blocks.py
# Purpose: structural document model — one block per heading/paragraph/list item/quote —
#          plus the split-sentences utility shared by detection and plagiarism.
# Exports: Block, BlockType, split_sentences

import re

from pydantic import BaseModel

BlockType = "heading | paragraph | list_item | blockquote"
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_ABBR = re.compile(r"\b(?:Mr|Mrs|Dr|Ms|St|vs|etc|e\.g|i\.e|Jr|Sr)\.$", re.IGNORECASE)
_INITIAL = re.compile(r"\b[A-Z]\.$")


class Block(BaseModel):
    index: int
    type: str  # one of BlockType
    text: str
    level: int | None = None  # heading depth 1-6
    ai_score: float | None = None
    reason: str | None = None


def split_sentences(text: str) -> list[str]:
    """Split on sentence enders, keeping abbreviations and initials intact."""
    parts = _SENTENCE_END.split(text.strip())
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if out and _ABBR.search(out[-1]):
            out[-1] = f"{out[-1]} {part}"
        elif out and _INITIAL.search(out[-1]) and len(out[-1]) <= 3:
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return out
