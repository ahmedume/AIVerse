# backend/tests/test_chat.py
# Purpose: conversation CRUD, ownership, SSE streaming (fake model), regenerate.

import json
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.core import llm


class FakeModel:
    """Duck-typed stand-in for a langchain chat model: yields token events."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.prompt: list | None = None

    async def astream_events(self, messages: list, version: str):  # noqa: ARG002
        self.prompt = messages
        async def gen():
            for token in self.tokens:
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": SimpleNamespace(content=token)},
                }
        return gen()


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


async def create_conversation(client: AsyncClient, **overrides) -> str:
    payload = {"agent_type": "chat", **overrides}
    response = await client.post("/conversations", json=payload)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def install_fake(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tokens: list[str]
) -> FakeModel:
    fake = FakeModel(tokens)
    monkeypatch.setattr(llm, "get_chat_model", lambda *a, **k: fake)
    return fake


# --- conversation CRUD ---------------------------------------------------------

async def test_create_conversation_defaults(client: AsyncClient) -> None:
    await register_user(client, "crud@example.com")
    response = await client.post("/conversations", json={})
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["title"] == "New conversation"
    assert data["agent_type"] == "chat"
    assert data["provider"] == "zen"
    assert data["model"] == "deepseek-v4-flash-free"
    assert data["message_count"] == 0


async def test_list_conversations_newest_first(client: AsyncClient) -> None:
    await register_user(client, "list@example.com")
    first = await create_conversation(client, title="First")
    second = await create_conversation(client, title="Second")
    response = await client.get("/conversations")
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()["data"]]
    assert ids == [second, first]


async def test_get_conversation_detail_and_messages(client: AsyncClient) -> None:
    await register_user(client, "detail@example.com")
    conversation_id = await create_conversation(client)
    response = await client.get(f"/conversations/{conversation_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["conversation"]["id"] == conversation_id
    assert data["messages"] == []
    response = await client.get(f"/conversations/{conversation_id}/messages")
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_rename_conversation(client: AsyncClient) -> None:
    await register_user(client, "rename@example.com")
    conversation_id = await create_conversation(client)
    response = await client.patch(
        f"/conversations/{conversation_id}", json={"title": "Renamed"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["title"] == "Renamed"
    response = await client.patch(f"/conversations/{conversation_id}", json={"title": ""})
    assert response.status_code == 422


async def test_delete_conversation(client: AsyncClient) -> None:
    await register_user(client, "del@example.com")
    conversation_id = await create_conversation(client)
    response = await client.delete(f"/conversations/{conversation_id}")
    assert response.status_code == 200
    response = await client.get(f"/conversations/{conversation_id}")
    assert response.status_code == 404


async def test_ownership_forbidden(client: AsyncClient) -> None:
    await register_user(client, "owner@example.com")
    conversation_id = await create_conversation(client)
    await register_user(client, "intruder@example.com")
    for method, path in (
        ("GET", f"/conversations/{conversation_id}"),
        ("PATCH", f"/conversations/{conversation_id}"),
        ("DELETE", f"/conversations/{conversation_id}"),
        ("GET", f"/conversations/{conversation_id}/messages"),
    ):
        response = await client.request(method, path,
                                        json={"title": "x"} if method == "PATCH" else None)
        assert response.status_code == 403


# --- SSE streaming ------------------------------------------------------------

async def test_chat_streams_and_persists(client: AsyncClient, monkeypatch) -> None:
    await register_user(client, "chat@example.com")
    fake = install_fake(client, monkeypatch, ["Hello", ", ", "world!"])
    response = await client.post("/chat", json={"message": "hi"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names[1:-1] == ["token", "token", "token"]
    assert names[-1] == "done"

    meta = events[0][1]
    assert meta["agent_type"] == "chat"
    assert meta["provider"] == "zen"
    assert meta["model"] == "deepseek-v4-flash-free"
    assert "".join(data["text"] for name, data in events if name == "token") == "Hello, world!"

    done = events[-1][1]
    assert done["token_count"] > 0

    assert len(fake.prompt) == 1
    assert fake.prompt[0].content == "hi"

    conversation_id = meta["conversation_id"]
    response = await client.get(f"/conversations/{conversation_id}")
    messages = response.json()["data"]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "hi"
    assert messages[1]["content"] == "Hello, world!"
    assert messages[1]["token_count"] > 0
    response = await client.get("/conversations")
    listed = response.json()["data"][0]
    assert listed["id"] == conversation_id
    assert listed["title"] == "hi"
    assert listed["message_count"] == 2


async def test_chat_appends_to_existing_conversation(client: AsyncClient, monkeypatch) -> None:
    await register_user(client, "multi@example.com")
    conversation_id = await create_conversation(client)
    install_fake(client, monkeypatch, ["first reply"])
    response = await client.post("/chat", json={"conversation_id": conversation_id,
                                                "message": "one"})
    assert response.status_code == 200
    install_fake(client, monkeypatch, ["second reply"])
    response = await client.post("/chat", json={"conversation_id": conversation_id,
                                                "message": "two"})
    assert response.status_code == 200
    response = await client.get(f"/conversations/{conversation_id}/messages")
    messages = response.json()["data"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in messages] == ["one", "first reply", "two", "second reply"]


async def test_regenerate_replaces_last_assistant(client: AsyncClient, monkeypatch) -> None:
    await register_user(client, "regen@example.com")
    conversation_id = await create_conversation(client)
    install_fake(client, monkeypatch, ["old answer"])
    response = await client.post("/chat", json={"conversation_id": conversation_id,
                                                "message": "question"})
    assert response.status_code == 200
    install_fake(client, monkeypatch, ["new answer"])
    response = await client.post("/chat", json={"conversation_id": conversation_id,
                                                "regenerate": True})
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert "".join(d["text"] for n, d in events if n == "token") == "new answer"
    response = await client.get(f"/conversations/{conversation_id}/messages")
    messages = response.json()["data"]
    assert [m["content"] for m in messages] == ["question", "new answer"]


async def test_regenerate_without_messages_emits_error(client: AsyncClient, monkeypatch) -> None:
    await register_user(client, "empty@example.com")
    install_fake(client, monkeypatch, ["x"])
    response = await client.post("/chat", json={"regenerate": True})
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "VALIDATION_ERROR"


async def test_chat_foreign_conversation_forbidden(client: AsyncClient, monkeypatch) -> None:
    await register_user(client, "owner2@example.com")
    conversation_id = await create_conversation(client)
    await register_user(client, "intruder2@example.com")
    install_fake(client, monkeypatch, ["x"])
    response = await client.post("/chat", json={"conversation_id": conversation_id,
                                                "message": "steal"})
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "FORBIDDEN"


async def test_chat_provider_not_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "noprov@example.com")
    conversation_id = await create_conversation(client, provider="openai")
    monkeypatch.setattr(llm.settings, "FALLBACK_PROVIDER", "")
    response = await client.post("/chat", json={"conversation_id": conversation_id,
                                                "message": "hi"})
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "PROVIDER_NOT_CONFIGURED"


async def test_chat_unknown_provider(client: AsyncClient) -> None:
    await register_user(client, "badprov@example.com")
    response = await client.post("/chat", json={"message": "hi", "provider": "mystery"})
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "UNKNOWN_PROVIDER"


async def test_chat_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401