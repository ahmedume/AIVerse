# backend/tests/test_agents.py
# Purpose: agent mode — tool-calling loop, SSE tool events, loop caps, tool failures.

import json

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessageChunk, HumanMessage

from app.core import llm, vector_store
from app.services import chat_service


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


class FakeAgentModel:
    """Scripted agent model: each astream_events call pops one scripted turn."""

    def __init__(self, script: list[dict]) -> None:
        self.script = script
        self.prompt: list | None = None

    def bind_tools(self, tools):  # noqa: ARG002
        return self

    async def astream_events(self, messages, version):  # noqa: ARG002
        self.prompt = messages
        turn = self.script.pop(0)

        async def gen():
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(
                    content=turn["content"],
                    tool_call_chunks=turn.get("tool_call_chunks", []),
                )},
            }
        return gen()


def tool_chunk(name: str, tool_call_id: str, args: str) -> list[dict]:
    return [{"index": 0, "name": name, "args": args, "id": tool_call_id}]


def install_agent_fake(
    monkeypatch: pytest.MonkeyPatch, script: list[dict]
) -> FakeAgentModel:
    fake = FakeAgentModel(script)
    monkeypatch.setattr(llm, "get_chat_model", lambda *a, **k: fake)
    return fake


async def create_agent_conversation(client: AsyncClient) -> str:
    response = await client.post("/conversations", json={"agent_type": "agent"})
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def test_agent_streams_tool_events_and_final_answer(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "agent@example.com")
    conversation_id = await create_agent_conversation(client)
    fake = install_agent_fake(monkeypatch, [
        {
            "content": "Let me check the time.",
            "tool_call_chunks": tool_chunk("current_datetime", "call_1", "{}"),
        },
        {"content": "The time is 2026-08-15 16:00:00 UTC.", "tool_call_chunks": []},
    ])
    response = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "What time is it?"}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert "tool_start" in names
    assert "tool_end" in names
    assert names[-1] == "done"
    assert "error" not in names

    start = next(data for name, data in events if name == "tool_start")
    end = next(data for name, data in events if name == "tool_end")
    assert start["tool"] == "current_datetime"
    assert start["tool_call_id"] == "call_1"
    assert end["tool"] == "current_datetime"

    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "Let me check the time.The time is 2026-08-15 16:00:00 UTC."
    humans = [m for m in fake.prompt if isinstance(m, HumanMessage)]
    assert humans[-1].content == "What time is it?"

    response = await client.get(f"/conversations/{conversation_id}/messages")
    messages = response.json()["data"]
    assert messages[-1]["content"] == "The time is 2026-08-15 16:00:00 UTC."


async def test_agent_loop_cap_honored(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "loopy@example.com")
    conversation_id = await create_agent_conversation(client)
    install_agent_fake(monkeypatch, [
        {"content": "", "tool_call_chunks": tool_chunk("current_datetime", f"call_{i}", "{}")}
        for i in range(8)
    ])
    response = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "loop"}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    tool_starts = [d for name, d in events if name == "tool_start"]
    assert len(tool_starts) == 4
    assert names[-1] == "done"
    assert "error" not in names

    response = await client.get(f"/conversations/{conversation_id}/messages")
    messages = response.json()["data"]
    assert messages[-1]["content"] == ""


async def test_agent_tool_failure_becomes_observation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "oops@example.com")
    conversation_id = await create_agent_conversation(client)
    install_agent_fake(monkeypatch, [
        {"content": "", "tool_call_chunks": tool_chunk("explode", "call_x", "{}")},
        {"content": "The tool failed but I am fine.", "tool_call_chunks": []},
    ])
    response = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "boom"}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert "tool_start" in names
    assert names[-1] == "done"
    assert "error" not in names
    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "The tool failed but I am fine."


async def test_agent_recursion_limit_emits_loop_limit_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "limit@example.com")
    conversation_id = await create_agent_conversation(client)
    monkeypatch.setattr(chat_service, "RECURSION_LIMIT", 6)
    install_agent_fake(monkeypatch, [
        {"content": "", "tool_call_chunks": tool_chunk("current_datetime", f"call_{i}", "{}")}
        for i in range(20)
    ])
    response = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "spin"}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "AGENT_LOOP_LIMIT"


async def test_agent_search_documents_uses_user_library(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "search@example.com")
    conversation_id = await create_agent_conversation(client)

    class FakeEmbeddings:
        async def aembed_query(self, query: str) -> list[float]:
            return [0.25] * 8

    calls: list[tuple[str, str]] = []

    def fake_search(user_id: str, query_vector: list[float], top_k: int) -> list[dict]:
        calls.append((user_id, str(top_k)))
        return [{"document_id": "d1", "filename": "notes.md",
                 "score": 0.9, "excerpt": "Nexus chunks documents into 800 chars."}]

    monkeypatch.setattr(llm, "get_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(vector_store, "search", fake_search)
    install_agent_fake(monkeypatch, [
        {"content": "", "tool_call_chunks": tool_chunk(
            "search_documents", "call_s", '{"query": "chunk size"}')},
        {"content": "Nexus uses 800-character chunks.", "tool_call_chunks": []},
    ])
    response = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "chunks?"}
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[-1] == "done"
    assert "error" not in names
    assert calls and calls[0][1] == "3"
    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "Nexus uses 800-character chunks."