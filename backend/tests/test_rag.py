# tests/test_rag.py
# Purpose: RAG service tests — chunking, vector store roundtrip, tools, agent routing.

import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app.core.blocks import Block
from app.services import rag_service, parse_service


class FakeEmbeddings:
    def __init__(self) -> None:
        self.vocab = {}

    def _vector(self, text: str) -> list[float]:
        tokens = text.lower().split()[:4]
        vector = [0.0] * 64
        for token in tokens:
            index = hash(token) % 64
            vector[index] += 1.0
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeModel(BaseChatModel):
    """Two-phase agent model: first a tool-calling message, then a final answer."""

    responses: list

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = self.responses.pop(0)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        return self

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self.responses.pop(0)
        if getattr(message, "tool_calls", None):
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_calls=message.tool_calls))
            return
        for piece in message.content.split(" "):
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece + " "))


def _blocks() -> list[Block]:
    return parse_service.resolve_source(
        {"text": "# Report\n\nArtificial intelligence detection results are strong in this section. "
                "The model found many uniform sentences here.\n\nA human wrote this second part with "
                "short, uneven, personal sentences that vary a lot. It reads naturally."}
    )[1]


def test_build_chunks_sizes_and_overlap():
    long_text = "Word " * 500
    blocks = [Block(index=0, type="paragraph", text=long_text)]
    chunks = rag_service.build_chunks(blocks, size=800, overlap=100)
    assert len(chunks) >= 2
    assert all(len(c["text"]) <= 800 for c in chunks)
    assert all(c["block_index"] == 0 for c in chunks)
    assert chunks[1]["text"].startswith(chunks[0]["text"][-100:])


def test_build_chunks_skips_headings():
    blocks = [Block(index=0, type="heading", text="Title"), Block(index=1, type="paragraph", text="Body text here.")]
    assert [c["block_index"] for c in rag_service.build_chunks(blocks)] == [1]


def test_vector_store_roundtrip(tmp_path):
    store = rag_service.VectorStore(tmp_path, FakeEmbeddings())
    chunks = rag_service.build_chunks(_blocks())
    store.build(chunks)
    assert store.index_path.exists() and store.meta_path.exists()

    reloaded = rag_service.VectorStore(tmp_path, FakeEmbeddings())
    assert reloaded.load()
    results = reloaded.search("artificial intelligence detection", k=4)
    assert results
    assert results[0]["block_index"] == 1
    assert "score" in results[0]


def test_vector_store_empty(tmp_path):
    store = rag_service.VectorStore(tmp_path / "empty", FakeEmbeddings())
    assert store.search("anything") == []
    assert store.load() is False


def test_route_tool_calls():
    state = {"messages": [AIMessage(content="", tool_calls=[{"name": "search_documents", "args": {}, "id": "1"}])]}
    assert rag_service._route(state) == "tools"
    assert rag_service._route({"messages": [AIMessage(content="done")]}) == rag_service.END


async def test_chat_stream_with_tool_loop_and_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_service, "get_embeddings", lambda: FakeEmbeddings())

    call = {"name": "search_documents", "args": {"query": "ai detection"}, "id": "call_1", "type": "tool_call"}
    model = FakeModel(responses=[
        AIMessage(content="", tool_calls=[call]),
        AIMessage(content="The first section reads like AI, change the opening."),
    ])
    context = rag_service._Context()
    store = rag_service.VectorStore(tmp_path, FakeEmbeddings())
    store.build(rag_service.build_chunks(_blocks()))
    context.models = [model.bind_tools(rag_service._make_tools(store, context))]

    graph = rag_service.build_graph(model, context)
    frames = []
    stream = graph.astream_events(
        {"messages": [HumanMessage(content="Where is AI content?")]},
        config={"recursion_limit": 30},
        version="v2",
    )
    async for event in stream:
        kind = event["event"]
        if kind in ("on_chat_model_stream", "on_tool_start", "on_tool_end"):
            frames.append(kind)
    assert "on_tool_start" in frames and "on_tool_end" in frames
    assert len([f for f in frames if f == "on_chat_model_stream"]) > 0
    assert context.sources


def test_chat_api_unknown_file_404(client):
    resp = client.post("/api/chat", json={"source": {"file_id": "0000000000000000"}, "question": "hi"})
    assert resp.status_code == 404
