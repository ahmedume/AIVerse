# tests/test_detect.py
# Purpose: detection service + API tests — blend math, fallback, SSE frames.

import json

from app.core.exceptions import EmptyDocumentError
from app.core.heuristics import heuristic_score
from app.services import detect_service, parse_service


def _frames(text: str) -> list[dict]:
    return [
        json.loads(line.split("data: ", 1)[1])
        for line in text.strip().split("\n\n")
        if line.startswith("data: ")
    ]


def test_parse_llm_score_json():
    assert detect_service._parse_llm_score('{"score": 85, "reason": "too uniform"}') == (85.0, "too uniform")


def test_parse_llm_score_bare():
    assert detect_service._parse_llm_score("score: 42 reason: flat") == (42.0, "LLM assessment")


def test_parse_llm_score_invalid_returns_none():
    assert detect_service._parse_llm_score("I think it looks human.") is None


def test_prompt_formats_with_json_braces():
    rendered = detect_service._PROMPT.format(text="sample")
    assert "TEXT:" in rendered and "sample" in rendered


def test_blend_math():
    heuristic = 50.0
    llm = 100.0
    assert round(0.6 * llm + 0.4 * heuristic, 1) == 80.0


async def test_detect_stream_sse_shape(monkeypatch):
    monkeypatch.setattr(detect_service, "_llm_score", lambda text: (90.0, "uniform"))
    text = "One two three four five six seven eight nine ten.\n\nOne two three four five six seven eight nine ten."
    blocks = parse_service.resolve_source({"text": text})[1]
    frames = _frames("".join([f async for f in detect_service.detect_stream(blocks)]))
    assert frames[0]["event"] == "meta"
    assert frames[0]["data"]["total"] == 2
    block_scores = [f for f in frames if f["event"] == "block_score"]
    assert len(block_scores) == 2
    for bs in block_scores:
        h = heuristic_score("One two three four five six seven eight nine ten.")
        assert bs["data"]["ai_score"] == round(0.6 * 90.0 + 0.4 * h, 1)
    done = frames[-1]
    assert done["event"] == "done"
    assert done["data"]["flagged"] is True


async def test_detect_stream_llm_failure_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setattr(detect_service, "_llm_score", lambda text: None)
    blocks = parse_service.resolve_source({"text": "Uniform uniform uniform uniform uniform uniform uniform uniform uniform uniform."})[1]
    frames = _frames("".join([f async for f in detect_service.detect_stream(blocks)]))
    bs = next(f for f in frames if f["event"] == "block_score")
    assert bs["data"]["reason"].startswith("Statistical heuristic")
    assert bs["data"]["ai_score"] == heuristic_score("Uniform uniform uniform uniform uniform uniform uniform uniform uniform uniform.")


async def test_detect_stream_empty_raises():
    import pytest

    with pytest.raises(EmptyDocumentError):
        parse_service.resolve_source({"text": "   "})


def test_detect_api_streams_events(client, monkeypatch):
    monkeypatch.setattr(detect_service, "_llm_score", lambda text: (30.0, "natural"))
    resp = client.post("/api/detect", json={"source": {"text": "First paragraph with plenty of words here.\n\nSecond paragraph also fine."}})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in resp.text.split("\n\n") if line.startswith("data: ")]
    assert events[0]["event"] == "meta"
    assert events[-1]["event"] == "done"
    assert len([e for e in events if e["event"] == "block_score"]) == 2


def test_detect_api_unknown_file_404(client):
    resp = client.post("/api/detect", json={"source": {"file_id": "0000000000000000"}})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
