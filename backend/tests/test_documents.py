# backend/tests/test_documents.py
# Purpose: document upload pipeline, rag mode with sources, textgen templates.

from io import BytesIO
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from pypdf import PdfWriter
from pypdf.generic import (
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)
from test_chat import create_conversation, parse_sse, register_user

from app.core import llm

EMBED_DIM = 8


class FakeEmbeddings:
    """Duck-typed stand-in for embeddings: deterministic vectors for all texts."""

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.25] * EMBED_DIM for _ in texts]

    async def aembed_query(self, text: str) -> list[float]:
        return [0.25] * EMBED_DIM


class FakeModel:
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


def install_fake(monkeypatch: pytest.MonkeyPatch, tokens: list[str] | None = None) -> FakeModel:
    fake = FakeModel(tokens or ["hello ", "world"])
    monkeypatch.setattr(llm, "get_chat_model", lambda *a, **k: fake)
    monkeypatch.setattr(llm, "get_embeddings", lambda: FakeEmbeddings())
    return fake


def make_pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    content = ContentStream(DecodedStreamObject(), page)
    content.operations = [
        ([NameObject("/F1"), NumberObject(12)], b"Tf"),
        ([NumberObject(72), NumberObject(100)], b"Td"),
        ([TextStringObject(text)], b"Tj"),
    ]
    page[NameObject("/Contents")] = content
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    page[NameObject("/Resources")] = resources
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


async def upload_document(client: AsyncClient, name: str, content: bytes) -> dict:
    response = await client.post(
        "/documents", files={"file": (name, content, "application/octet-stream")}
    )
    assert response.status_code == 201
    return response.json()["data"]


async def wait_ready(client: AsyncClient, document_id: str) -> dict:
    response = await client.get("/documents")
    assert response.status_code == 200
    for document in response.json()["data"]:
        if document["id"] == document_id:
            return document
    raise AssertionError(f"document {document_id} not listed")


# --- upload pipeline -----------------------------------------------------------

async def test_upload_txt_ready(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    await register_user(client, "upload@example.com")
    install_fake(monkeypatch)
    data = await upload_document(
        client,
        "notes.txt",
        b"Nexus is a self-hosted AI workspace with chat, rag, agents and templates.",
    )
    document = await wait_ready(client, data["id"])
    assert document["status"] == "ready"
    assert document["chunk_count"] >= 1
    assert document["filename"] == "notes.txt"


async def test_upload_pdf_ready(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    await register_user(client, "pdf@example.com")
    install_fake(monkeypatch)
    data = await upload_document(client, "report.pdf", make_pdf("RAG pipeline summary."))
    document = await wait_ready(client, data["id"])
    assert document["status"] == "ready"
    assert document["chunk_count"] >= 1


async def test_upload_rejects_invalid_type(client: AsyncClient) -> None:
    await register_user(client, "badtype@example.com")
    response = await client.post(
        "/documents", files={"file": ("virus.exe", b"MZ", "application/octet-stream")}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE_TYPE"


async def test_upload_rejects_oversize(client: AsyncClient) -> None:
    await register_user(client, "bigfile@example.com")
    response = await client.post(
        "/documents", files={"file": ("big.txt", b"x" * 4096, "text/plain")}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_document_list_and_delete(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "del@example.com")
    install_fake(monkeypatch)
    data = await upload_document(client, "keep.txt", b"content to index")
    document = await wait_ready(client, data["id"])
    assert document["status"] == "ready"
    response = await client.delete(f"/documents/{data['id']}")
    assert response.status_code == 200
    response = await client.get("/documents")
    assert response.json()["data"] == []


async def test_foreign_document_delete_forbidden(client: AsyncClient) -> None:
    await register_user(client, "docowner@example.com")
    data = await upload_document(client, "mine.txt", b"mine")
    await register_user(client, "docother@example.com")
    response = await client.delete(f"/documents/{data['id']}")
    assert response.status_code == 404


# --- rag mode ------------------------------------------------------------------

async def test_rag_streams_with_sources(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "rag@example.com")
    install_fake(monkeypatch)
    await upload_document(
        client, "faq.txt", b"Chunk size is 800 characters with 100 overlap in Nexus."
    )
    conversation_id = await create_conversation(client, agent_type="rag")
    response = await client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "What chunk size does Nexus use?",
        },
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    sources_index = names.index("sources")
    if "token" in names:
        assert sources_index < names.index("token")
    sources = dict(events)["sources"]
    assert len(sources) == 1
    assert sources[0]["filename"] == "faq.txt"
    assert sources[0]["document_id"]
    assert 0 <= sources[0]["score"] <= 1.0001
    assert "chunk size" in sources[0]["excerpt"].lower()
    assert events[-1][0] == "done"


async def test_rag_no_documents_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "ragnone@example.com")
    install_fake(monkeypatch)
    conversation_id = await create_conversation(client, agent_type="rag")
    response = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "hi"}
    )
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "NO_DOCUMENTS"


async def test_rag_ignores_foreign_documents(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "ragowner@example.com")
    install_fake(monkeypatch)
    await upload_document(client, "secret.txt", b"Only the owner may retrieve this.")
    await register_user(client, "ragother@example.com")
    conversation_id = await create_conversation(client, agent_type="rag")
    response = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "secret"}
    )
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "NO_DOCUMENTS"


# --- textgen mode --------------------------------------------------------------

async def test_textgen_requires_template_id(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "tg@example.com")
    install_fake(monkeypatch)
    conversation_id = await create_conversation(client, agent_type="textgen")
    response = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "hi"}
    )
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "VALIDATION_ERROR"


async def test_textgen_streams_rendered_template(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "tg2@example.com")
    fake = install_fake(monkeypatch)
    response = await client.post(
        "/templates",
        json={"name": "summarize", "content": "Summarize {input} in 5 bullets."},
    )
    assert response.status_code == 201
    template_id = response.json()["data"]["id"]
    conversation_id = await create_conversation(client, agent_type="textgen")
    response = await client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "template_id": template_id,
            "message": "the nexus project",
        },
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "done"
    assert fake.prompt is not None
    assert fake.prompt[0].content == "Summarize the nexus project in 5 bullets."


async def test_textgen_foreign_template_forbidden(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register_user(client, "tgowner@example.com")
    install_fake(monkeypatch)
    response = await client.post(
        "/templates", json={"name": "mine", "content": "Do {input} please."}
    )
    template_id = response.json()["data"]["id"]
    await register_user(client, "tgother@example.com")
    conversation_id = await create_conversation(client, agent_type="textgen")
    response = await client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "template_id": template_id,
            "message": "x",
        },
    )
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "FORBIDDEN"


# --- templates CRUD ------------------------------------------------------------

async def test_template_crud(client: AsyncClient) -> None:
    await register_user(client, "tpl@example.com")
    response = await client.post(
        "/templates", json={"name": "translate", "content": "Translate {input} to French."}
    )
    assert response.status_code == 201
    template_id = response.json()["data"]["id"]
    response = await client.get("/templates")
    assert len(response.json()["data"]) == 1
    response = await client.put(
        f"/templates/{template_id}",
        json={"name": "translate-fr", "content": "Translate {input} to French only."},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "translate-fr"
    response = await client.delete(f"/templates/{template_id}")
    assert response.status_code == 204
    response = await client.get("/templates")
    assert response.json()["data"] == []


async def test_template_requires_placeholder(client: AsyncClient) -> None:
    await register_user(client, "tplbad@example.com")
    response = await client.post(
        "/templates", json={"name": "broken", "content": "No placeholder here"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TEMPLATE_MISSING_PLACEHOLDER"


async def test_template_name_unique_per_user(client: AsyncClient) -> None:
    await register_user(client, "tplone@example.com")
    payload = {"name": "same", "content": "Do {input} nicely."}
    response = await client.post("/templates", json=payload)
    assert response.status_code == 201
    response = await client.post("/templates", json=payload)
    assert response.status_code == 409
    await register_user(client, "tpltwo@example.com")
    response = await client.post("/templates", json=payload)
    assert response.status_code == 201