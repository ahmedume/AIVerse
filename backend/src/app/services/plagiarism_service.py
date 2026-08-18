# src/app/services/plagiarism_service.py
# Purpose: DuckDuckGo-based plagiarism scan — sentence-aligned ~120-word fragments,
#          8-token n-gram overlap matching, streamed as SSE. Best-effort: DDG
#          failures yield checked=false flags, never a hard error.
# Exports: build_fragments, plagiarism_stream

import asyncio
import html
import re
import urllib.parse
from collections.abc import AsyncIterator
from html.parser import HTMLParser

import httpx

from app.core.blocks import Block, split_sentences
from app.core.sse import sse
from app.services import parse_service

_FRAGMENT_WORDS = 120
_MAX_FRAGMENTS = 40
_SPACING_S = 1.5
_TIMEOUT_S = 10
_NGRAM = 8
_MAX_RESULTS = 20
_WORD_RE = re.compile(r"[a-z0-9']+")

_DDG_QUERY = "https://html.duckduckgo.com/html/?q={query}"


def build_fragments(blocks: list[Block]) -> list[str]:
    """Sentence-aligned fragments of ~120 words, max 40; skips headings."""
    text_blocks = [b.text for b in blocks if b.type in ("paragraph", "list_item", "blockquote")]
    sentences = [s for text in text_blocks for s in split_sentences(text)]
    fragments: list[str] = []
    current: list[str] = []
    words = 0
    for sentence in sentences:
        current.append(sentence)
        words += len(sentence.split())
        if words >= _FRAGMENT_WORDS or (current and words >= _FRAGMENT_WORDS // 2 and len(fragments) >= _MAX_FRAGMENTS - 1):
            fragments.append(" ".join(current))
            current, words = [], 0
        if len(fragments) >= _MAX_FRAGMENTS:
            break
    if current and len(fragments) < _MAX_FRAGMENTS:
        fragments.append(" ".join(current))
    return fragments


class _ResultParser(HTMLParser):
    """Collects DDG html result links (result__a) and snippets (result__snippet)."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._in_link = False
        self._in_snippet = False
        self._current: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = dict(attrs).get("class", "") or ""
        if tag == "a" and "result__a" in classes:
            self._in_link = True
            self._current = {"href": "", "title": "", "snippet": ""}
            self.results.append(self._current)
        elif tag == "a" and "result__snippet" in classes:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_link = False
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_link and self._current is not None:
            self._current["title"] += data
        elif self._in_snippet and self._current is not None:
            self._current["snippet"] += data


def _clean_url(raw: str) -> str:
    unquoted = urllib.parse.unquote(raw)
    match = re.search(r"uddg=([^&]+)", unquoted)
    return match.group(1) if match else unquoted


def parse_results(page: str) -> list[dict]:
    """Parse DDG html results into [{url, title, snippet}]."""
    parser = _ResultParser()
    parser.feed(page)
    out = []
    for item in parser.results:
        if item["title"].strip():
            out.append(
                {
                    "url": _clean_url(item["href"]),
                    "title": html.unescape(item["title"].strip()),
                    "snippet": html.unescape(item["snippet"].strip())[:500],
                }
            )
    return out


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _ngrams(tokens: list[str], size: int = _NGRAM) -> list[tuple[str, ...]]:
    return [tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)]


def match_fragment(fragment: str, results: list[dict]) -> list[dict]:
    """Filter results whose snippet/title share an 8-token n-gram with the fragment."""
    fragment_ngrams = set(_ngrams(_tokens(fragment)))
    if not fragment_ngrams:
        return []
    matched: list[dict] = []
    for result in results:
        candidate = _ngrams(_tokens(f"{result['title']} {result['snippet']}"))
        if any(ng in fragment_ngrams for ng in candidate):
            matched.append(result)
    return matched[: _MAX_RESULTS]


async def _search_fragment(client: httpx.AsyncClient, fragment: str, max_results: int) -> dict:
    await asyncio.sleep(_SPACING_S)
    query = urllib.parse.quote(fragment[:200])
    try:
        response = await client.get(_DDG_QUERY.format(query=query))
        response.raise_for_status()
        results = parse_results(response.text)
        matches = match_fragment(fragment, results)
        return {
            "checked": True,
            "matches": matches[:max_results],
            "matched": bool(matches),
            "total_results": len(results),
        }
    except httpx.HTTPError:
        return {"checked": False, "matches": [], "matched": False, "total_results": 0}


async def plagiarism_stream(source: dict, max_results: int = 5) -> AsyncIterator[str]:
    _, blocks = parse_service.resolve_source(source)
    fragments = build_fragments(blocks)
    yield sse({"event": "meta", "data": {"total": len(fragments), "best_effort": True}})
    if not fragments:
        yield sse({"event": "done", "data": {"checked": 0, "matched": 0, "matches": []}})
        return

    async with httpx.AsyncClient(timeout=_TIMEOUT_S, headers={"User-Agent": "Mozilla/5.0"}) as client:
        checked = 0
        matched_fragments = 0
        all_matches: list[dict] = []
        for index, fragment in enumerate(fragments):
            result = await _search_fragment(client, fragment, max_results)
            if result["checked"]:
                checked += 1
                matched_fragments += int(result["matched"])
                all_matches.extend(result["matches"])
            yield sse({"event": "fragment", "data": {"index": index, **result}})

    best = all_matches[0] if all_matches else None
    yield sse(
        {
            "event": "done",
            "data": {
                "checked": checked,
                "matched": matched_fragments,
                "total_fragments": len(fragments),
                "best_match_url": best["url"] if best else None,
                "matches": all_matches[: max_results * 4],
            },
        }
    )