# backend/tests/test_fallback.py
# Purpose: LLM fallback chain — a failing/unconfigured primary provider falls
#          back to the configured fallback provider (e.g. Zen -> Gemini).

import json

import httpx
import openai
import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessageChunk
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core import llm


def rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError(
        "rate limited",
        response=httpx.Response(429, request=httpx.Request("POST", "http://zen.local/v1")),
        body=None,
    )


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.split("\n")
        name = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((name, data))
    return events


async def register_user(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": "secure-password-123"},
    )
    assert response.status_code == 201


class FlakyModel:
    """Raises before any token — simulates rate limit / auth / connection failure."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def astream_events(self, messages, version):  # noqa: ARG002
        raise self.error


class StreamingModel:
    def __init__(self, text: str) -> None:
        self.text = text

    def bind_tools(self, tools):  # noqa: ARG002
        return self

    async def astream_events(self, messages, version):  # noqa: ARG002
        async def gen():
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content=self.text)},
            }
        return gen()


class DiesMidStreamModel:
    """Yields one token, then fails — mid-stream failures must NOT fall back."""

    async def astream_events(self, messages, version):  # noqa: ARG002
        async def gen():
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content="partial ")},
            }
            raise rate_limit_error()
        return gen()


async def test_primary_failure_falls_back_to_second_candidate(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "fallback@example.com")
    monkeypatch.setattr(llm, "get_model_chain", lambda *a, **k: [
        FlakyModel(rate_limit_error()),
        StreamingModel("Hello from the fallback provider."),
    ])
    response = await client.post(
        "/chat", json={"message": "hi"}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names[-1] == "done"
    assert "error" not in names
    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "Hello from the fallback provider."


async def test_mid_stream_failure_is_not_fallback(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "midstream@example.com")
    monkeypatch.setattr(llm, "get_model_chain", lambda *a, **k: [DiesMidStreamModel()])
    response = await client.post(
        "/chat", json={"message": "hi"}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "MODEL_RATE_LIMITED"


async def test_all_candidates_failing_emits_error_event(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "allfail@example.com")
    monkeypatch.setattr(llm, "get_model_chain", lambda *a, **k: [
        FlakyModel(rate_limit_error()),
        FlakyModel(RuntimeError("gemini down")),
    ])
    response = await client.post(
        "/chat", json={"message": "hi"}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "MODEL_RATE_LIMITED"


async def test_empty_chain_emits_provider_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "noprovider@example.com")
    monkeypatch.setattr(llm, "get_model_chain", lambda *a, **k: [])
    response = await client.post(
        "/chat", json={"message": "hi"}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "PROVIDER_NOT_CONFIGURED"


def test_get_model_chain_orders_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm.settings, "ZEN_API_KEY", "zk")
    monkeypatch.setattr(llm.settings, "ZEN_BASE_URL", "http://zen.local/v1")
    monkeypatch.setattr(llm.settings, "GEMINI_API_KEY", "gk")
    monkeypatch.setattr(llm.settings, "FALLBACK_PROVIDER", "gemini")
    monkeypatch.setattr(llm.settings, "FALLBACK_MODEL", "gemini-2.5-flash")

    chain = llm.get_model_chain("zen", "deepseek-v4-flash-free", 0.5)
    assert len(chain) == 2
    assert isinstance(chain[0], ChatOpenAI)
    assert isinstance(chain[1], ChatGoogleGenerativeAI)

    monkeypatch.setattr(llm.settings, "GEMINI_API_KEY", "")
    assert len(llm.get_model_chain("zen", "deepseek-v4-flash-free")) == 1

    monkeypatch.setattr(llm.settings, "GEMINI_API_KEY", "gk")
    monkeypatch.setattr(llm.settings, "FALLBACK_MODEL", "")
    assert len(llm.get_model_chain("zen", "deepseek-v4-flash-free")) == 1

    monkeypatch.setattr(llm.settings, "FALLBACK_PROVIDER", "zen")
    assert len(llm.get_model_chain("zen", "deepseek-v4-flash-free")) == 1

    monkeypatch.setattr(llm.settings, "ZEN_API_KEY", "")
    monkeypatch.setattr(llm.settings, "ZEN_BASE_URL", "")
    monkeypatch.setattr(llm.settings, "FALLBACK_PROVIDER", "gemini")
    monkeypatch.setattr(llm.settings, "FALLBACK_MODEL", "gemini-2.5-flash")
    chain = llm.get_model_chain("zen", "deepseek-v4-flash-free")
    assert len(chain) == 1
    assert isinstance(chain[0], ChatGoogleGenerativeAI)