# src/app/core/heuristics.py
# Purpose: statistical AI-likeness features (no LLM) per SDS §6 — burstiness,
#          type-token ratio, bigram repetition, transition phrases, punctuation.
# Exports: heuristic_score

import re
import statistics
from collections import Counter

from app.core.blocks import split_sentences

_TRANSITIONS = (
    "moreover", "furthermore", "in addition", "additionally", "in conclusion",
    "consequently", "therefore", "nevertheless", "nonetheless", "overall",
    "in summary", "as a result", "for instance", "in contrast", "notably",
)
_TRANS_RE = re.compile(r"\b(?:" + "|".join(_TRANSITIONS) + r")\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9']+")
_PUNCT_VARIETY = set(".,!?;:—()\"'")


def heuristic_score(text: str) -> float:
    """0-100 AI-likeness from statistical signals; 50 when unmeasurable."""
    words = _WORD_RE.findall(text.lower())
    if len(words) < 10:
        return 50.0

    lengths = [len(s.split()) for s in split_sentences(text) if s.split()]
    if len(lengths) >= 2:
        mean = statistics.mean(lengths)
        burst = 100.0 if mean == 0 else max(0.0, 100.0 - (statistics.pstdev(lengths) / mean) * 90.0)
    else:
        burst = 100.0

    ttr = len(set(words)) / len(words)
    ttr_score = max(0.0, min(100.0, (0.92 - ttr) * 160.0))

    bigrams = Counter(zip(words, words[1:], strict=False))
    top = max(bigrams.values(), default=0)
    rep = max(0.0, min(100.0, top / max(len(words) / 20.0, 1.0) * 25.0))

    trans = max(0.0, min(100.0, len(_TRANS_RE.findall(text)) / len(words) * 400.0))

    punct = max(0.0, 100.0 - sum(1 for p in _PUNCT_VARIETY if p in text) * 12.0)

    return round(0.30 * burst + 0.25 * ttr_score + 0.20 * rep + 0.15 * trans + 0.10 * punct, 1)
