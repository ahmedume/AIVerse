# tests/test_plagiarism.py
# Purpose: plagiarism service + API tests — fragments, HTML parsing, matching, resilience.

import json

from app.core.blocks import Block
from app.services import parse_service, plagiarism_service

_DDG_PAGE = """
<html><body>
<div class="result results_links">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpaper&amp;rut=abc">Example Paper Title</a>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpaper">The quick brown fox jumps over the lazy dog again and again.</a>
</div>
</body></html>
"""


def _blocks_from_text(text: str) -> list[Block]:
    return parse_service.resolve_source({"text": text})[1]


def test_fragments_sentence_aligned_120_words():
    text = " ".join([f"Sentence number {i} with some extra words here." for i in range(30)])
    fragments = plagiarism_service.build_fragments(_blocks_from_text(text))
    assert len(fragments) >= 2
    for fragment in fragments:
        assert 100 <= len(fragment.split()) <= 140


def test_fragments_skip_headings():
    blocks = [
        Block(index=0, type="heading", text="Introduction"),
        Block(index=1, type="paragraph", text="Body text with enough words here to be included."),
    ]
    fragments = plagiarism_service.build_fragments(blocks)
    assert fragments == ["Body text with enough words here to be included."]


def test_fragments_cap_at_40():
    text = " ".join([f"Word block {i} repeated content." for i in range(400)])
    fragments = plagiarism_service.build_fragments(_blocks_from_text(text))
    assert len(fragments) <= 40


def test_parse_ddg_results():
    results = plagiarism_service.parse_results(_DDG_PAGE)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/paper"
    assert results[0]["title"] == "Example Paper Title"


def test_match_fragment_ngram_overlap():
    fragment = "The quick brown fox jumps over the lazy dog again and again."
    results = [{"url": "https://a.example/x", "title": "Fox stories", "snippet": "The quick brown fox jumps over the lazy dog again and again."}]
    assert plagiarism_service.match_fragment(fragment, results) == results


def test_match_fragment_no_overlap():
    fragment = "The quick brown fox jumps over the lazy dog again and again."
    results = [{"url": "https://a.example/x", "title": "Cooking", "snippet": "Recipes for pasta with tomato sauce and basil."}]
    assert plagiarism_service.match_fragment(fragment, results) == []


def test_match_fragment_short_input_no_false_positive():
    assert plagiarism_service.match_fragment("short text", []) == []


async def test_plagiarism_stream_ddg_down_flags_checked_false(monkeypatch):
    async def _fake_search(client, fragment, max_results):
        return {"checked": False, "matches": [], "matched": False, "total_results": 0}

    monkeypatch.setattr(plagiarism_service, "_search_fragment", _fake_search)
    frames = []
    async for frame in plagiarism_service.plagiarism_stream({"text": "One two three. Four five six."}):
        frames.append(json.loads(frame.split("data: ", 1)[1]))
    assert frames[0]["event"] == "meta"
    fragments = [f for f in frames if f["event"] == "fragment"]
    assert fragments and all(f["data"]["checked"] is False for f in fragments)
    done = frames[-1]
    assert done["event"] == "done"
    assert done["data"]["checked"] == 0


async def test_plagiarism_stream_counts_matches(monkeypatch):
    async def _fake_search(client, fragment, max_results):
        return {
            "checked": True,
            "matches": [{"url": "https://a.example/1", "title": "t", "snippet": "s"}],
            "matched": True,
            "total_results": 3,
        }

    monkeypatch.setattr(plagiarism_service, "_search_fragment", _fake_search)
    frames = []
    async for frame in plagiarism_service.plagiarism_stream({"text": "First fragment words. Second fragment words."}):
        frames.append(json.loads(frame.split("data: ", 1)[1]))
    done = frames[-1]["data"]
    assert done["checked"] == len([f for f in frames if f["event"] == "fragment"])
    assert done["matched"] == done["checked"]
    assert done["best_match_url"] == "https://a.example/1"


def test_plagiarism_api_streams(client, monkeypatch):
    async def _fake_search(client, fragment, max_results):
        return {"checked": True, "matches": [], "matched": False, "total_results": 0}

    monkeypatch.setattr(plagiarism_service, "_search_fragment", _fake_search)
    resp = client.post("/api/plagiarism", json={"source": {"text": "A single fragment with plenty of words here to make it real."}})
    assert resp.status_code == 200
    events = [json.loads(line[6:]) for line in resp.text.split("\n\n") if line.startswith("data: ")]
    assert events[0]["event"] == "meta"
    assert events[-1]["event"] == "done"
    assert [e["event"] for e in events[1:-1]] == ["fragment"]


def test_plagiarism_api_unknown_file_404(client):
    resp = client.post("/api/plagiarism", json={"source": {"file_id": "0000000000000000"}})
    assert resp.status_code == 404