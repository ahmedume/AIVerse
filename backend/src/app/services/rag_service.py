# src/app/services/rag_service.py
# Purpose: RAG chatbot � FAISS vector store over uploaded documents, LangGraph
#          agent (StateGraph + tools) streamed to SSE. Chunking 800/100, top_k=4,
#          5-iteration tool guard, retry/timeout policies per SKILL.md.
# Exports: build_chunks, VectorStore, chat_stream

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import RetryPolicy, TimeoutPolicy

from app.core.config import get_settings
from app.core.heuristics import heuristic_score
from app.core.llm import get_embeddings, get_model_chain
from app.core.sse import sse
from app.services import parse_service
from app.services.humanize_service import _chunk_text

settings = get_settings()

logger = logging.getLogger("app")

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100
_TOP_K = 4
_TOOL_LIMIT = 5
_RUN_NAME = "aiverse_chat"

INDEX_CACHE: dict[str, "VectorStore"] = {}
_INDEX_LOCK = asyncio.Lock()


def build_chunks(
    blocks: list, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP
) -> list[dict]:
    chunks: list[dict] = []
    for block in blocks:
        if block.type not in ("paragraph", "list_item", "blockquote"):
            continue
        text = block.text
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunks.append({"text": text[start:end], "block_index": block.index})
            if end == len(text):
                break
            start = end - overlap
    return chunks


class VectorStore:
    """FAISS (inner-product, normalized) index + meta.jsonl on disk."""

    def __init__(self, folder: Path, embeddings) -> None:
        self.folder = folder
        self.embeddings = embeddings
        self.index: faiss.Index | None = None
        self.meta: list[dict] = []

    @property
    def index_path(self) -> Path:
        return self.folder / "index.faiss"

    @property
    def meta_path(self) -> Path:
        return self.folder / "meta.jsonl"

    def build(self, chunks: list[dict]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        if not chunks:
            self.index = faiss.IndexFlatIP(1)
            self.meta = []
            self._persist()
            return
        vectors = self.embeddings.embed_documents([c["text"] for c in chunks])
        matrix = np.asarray(vectors, dtype=np.float32)
        faiss.normalize_L2(matrix)
        self.index = faiss.IndexFlatIP(matrix.shape[1])
        self.index.add(matrix)
        self.meta = [
            {"text": c["text"], "block_index": c["block_index"], "excerpt": c["text"][:300]}
            for c in chunks
        ]
        self._persist()

    def _persist(self) -> None:
        faiss.write_index(self.index, str(self.index_path))
        with self.meta_path.open("w", encoding="utf-8") as handle:
            for item in self.meta:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    def load(self) -> bool:
        if not self.index_path.exists() or not self.meta_path.exists():
            return False
        self.index = faiss.read_index(str(self.index_path))
        self.meta = [
            json.loads(line)
            for line in self.meta_path.read_text(encoding="utf-8").splitlines()
        ]
        return True

    def search(self, query: str, k: int = _TOP_K) -> list[dict]:
        if self.index is None or not self.meta or self.index.ntotal == 0:
            return []
        vector = np.asarray([self.embeddings.embed_query(query)], dtype=np.float32)
        faiss.normalize_L2(vector)
        scores, indices = self.index.search(vector, min(k, self.index.ntotal))
        return [
            {**self.meta[int(idx)], "score": round(float(score), 3)}
            for score, idx in zip(scores[0], indices[0], strict=True)
        ]


def _index_key(source: dict) -> str:
    if source.get("file_id"):
        return source["file_id"]
    text = (source.get("text") or "").encode("utf-8")
    return "text-" + hashlib.sha256(text).hexdigest()[:16]


async def _ensure_index(source: dict, blocks: list) -> VectorStore:
    key = _index_key(source)
    async with _INDEX_LOCK:
        if key in INDEX_CACHE:
            return INDEX_CACHE[key]
        folder = settings.vectorstore_dir / key
        store = VectorStore(folder, get_embeddings())
        if not store.load():
            chunks = build_chunks(blocks)
            await asyncio.to_thread(store.build, chunks)
        INDEX_CACHE[key] = store
        return store


def _route(state: dict) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


class _Context:
    """Holds per-request model chain and tool results."""

    def __init__(self) -> None:
        self.tools: list = []
        self.models: list = []
        self.sources: list[dict] = []


_SYSTEM_PROMPT = (
    "You are a document Q&A assistant. The user's document is available only "
    "through the search_documents and analyze_ai_content tools - you cannot see "
    "it otherwise. ALWAYS call search_documents (or analyze_ai_content for AI "
    "scoring) before answering a question about the document. Answer from the "
    "retrieved chunks only, cite chunk numbers when relevant, and keep answers "
    "concise. If a tool returns no relevant chunks, say so."
)


def build_graph(model, context: _Context) -> object:
    """StateGraph agent: model with tools, 5-iteration guard, retry policy."""

    def _tool_call_count(messages) -> int:
        return sum(1 for m in messages if getattr(m, "tool_calls", None))

    async def agent_node(state: dict):
        messages = state["messages"]
        prompt = [SystemMessage(content=_SYSTEM_PROMPT), *messages]
        if _tool_call_count(messages) >= _TOOL_LIMIT:
            return {
                "messages": [
                    AIMessage(
                        content="I've hit my tool-use limit for this question. "
                        "Here's my answer based on what I've already found."
                    )
                ]
            }
        last_error: str | None = None
        for model_candidate in context.models:
            try:
                collected: list[str] = []
                tool_calls: list = []
                async for chunk in model_candidate.astream(prompt):
                    piece = _chunk_text(getattr(chunk, "content", "") or "")
                    if piece:
                        collected.append(piece)
                    if getattr(chunk, "tool_calls", None):
                        tool_calls.extend(chunk.tool_calls)
                return {"messages": [AIMessage(content="".join(collected), tool_calls=tool_calls)]}
            except Exception as exc:
                last_error = str(exc)
                logger.warning("chat provider failed: %s", last_error)
                continue
        return {
            "messages": [
                AIMessage(
                    content=(
                        "We can't process your message right now because "
                        "you don't have enough credits."
                    )
                )
            ]
        }

    graph = StateGraph(MessagesState, context_schema=dict)
    graph.add_node(
        "agent",
        agent_node,
        retry_policy=RetryPolicy(max_attempts=2),
        timeout=TimeoutPolicy(run_timeout=60),
    )
    graph.add_node("tools", ToolNode(context.tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _route)
    graph.add_edge("tools", "agent")
    return graph.compile()


def _make_tools(store: VectorStore, context: _Context) -> list:
    @tool
    def search_documents(query: str) -> str:
        """Search the uploaded document for chunks relevant to the query."""
        results = store.search(query, k=min(3, _TOP_K))
        context.sources.extend(results)
        if not results:
            return "No relevant chunks found in the document."
        return "\n\n".join(f"[chunk {r['block_index']}] {r['text']}" for r in results)

    @tool
    def analyze_ai_content(query: str) -> str:
        """Score how AI-like the most relevant chunks are (0-100) and why."""
        results = store.search(query, k=1)
        if not results:
            return "No content to analyze."
        text = results[0]["text"]
        score = heuristic_score(text)
        verdict = "likely AI" if score >= 70 else "likely human" if score < 40 else "ambiguous"
        return f"chunk {results[0]['block_index']}: AI-likeness {score}/100 ({verdict})"

    @tool
    def current_datetime() -> str:
        """Return the current date and time."""
        return datetime.now().isoformat()

    context.tools = [search_documents, analyze_ai_content, current_datetime]
    return context.tools


async def chat_stream(source: dict, question: str) -> AsyncIterator[str]:
    _, blocks = parse_service.resolve_source(source)
    store = await _ensure_index(source, blocks)
    yield sse({"event": "meta", "data": {"question": question}})

    context = _Context()
    context.models = [
        model.bind_tools(_make_tools(store, context))
        for model in get_model_chain(
            settings.DEFAULT_PROVIDER, settings.DEFAULT_MODEL, temperature=0.4
        )
    ]
    graph = build_graph(context.models[0] if context.models else None, context)

    events: list[str] = []
    answer = ""
    try:
        stream = graph.astream_events(
            {"messages": [HumanMessage(content=question)]},
            config={"run_name": _RUN_NAME, "recursion_limit": 30},
            version="v2",
        )
        async for event in stream:
            kind = event["event"]
            events.append(kind)
            if kind == "on_chat_model_stream":
                piece = _chunk_text(event["data"]["chunk"].content)
                if piece:
                    answer += piece
                    yield sse({"event": "token", "data": {"token": piece}})
            elif kind == "on_tool_start":
                input_data = event["data"].get("input", {})
                yield sse(
                    {
                        "event": "tool_start",
                        "data": {"name": event["name"], "input": input_data},
                    }
                )
            elif kind == "on_tool_end":
                output = getattr(event["data"].get("output", ""), "content", "")
                yield sse(
                    {
                        "event": "tool_end",
                        "data": {"name": event["name"], "output": str(output)[:500]},
                    }
                )
            elif kind == "on_chain_end" and event.get("name") in ("LangGraph", _RUN_NAME):
                messages = (event["data"].get("output") or {}).get("messages") or []
                if messages:
                    last = messages[-1]
                    final_text = _chunk_text(getattr(last, "content", "") or "")
                    if final_text:
                        answer = answer or final_text
    except Exception:
        if not answer:
            answer = "I couldn't finish an answer. Please try again or check the API keys."

    yield sse(
        {
            "event": "sources",
            "data": {
                "items": [
                    {
                        "excerpt": r["excerpt"],
                        "block_index": r["block_index"],
                        "score": r.get("score"),
                    }
                    for r in context.sources[: _TOP_K]
                ]
            },
        }
    )
    yield sse({"event": "done", "data": {"answer": answer.strip(), "events": len(events)}})