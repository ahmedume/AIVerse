# src/app/agents/nodes.py
# Purpose: graph nodes — plain chat, rag retrieval, agent tool-calling loop.
#          Nodes emit `custom` stream events: token, sources, tool_start, tool_end.
# Exports: chat_node, retrieve_node, agent_node, tools_executor

import json
from collections.abc import Sequence
from typing import Any, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from app.agents.tools import current_datetime, search_documents
from app.agents.types import AgentContext, AgentState
from app.core import llm, vector_store
from app.core.exceptions import AppError
from app.schemas.template_schema import TEMPLATE_PLACEHOLDER

RAG_TOP_K = 4
RAG_SYSTEM_PROMPT = (
    "You are Nexus, an assistant that answers using the provided context. "
    "Ground your answer in the context and cite filenames. "
    "If the context does not answer the question, say you don't know."
)
MAX_AGENT_ITERATIONS = 5

TOOLS = {"search_documents": search_documents, "current_datetime": current_datetime}


def _merge_tool_call_chunks(chunks: list[dict[str, str]]) -> list[dict[str, object]]:
    """Reassemble streamed tool_call_chunks (indexed fragments) into tool_calls."""
    merged: dict[int, dict[str, str]] = {}
    for chunk in chunks:
        entry = merged.setdefault(int(chunk.get("index", 0)), {"name": "", "args": "", "id": ""})
        entry["name"] += chunk.get("name") or ""
        entry["args"] += chunk.get("args") or ""
        entry["id"] += chunk.get("id") or ""
    calls: list[dict[str, object]] = []
    for entry in merged.values():
        try:
            args = json.loads(entry["args"] or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append({"name": entry["name"], "args": args, "id": entry["id"]})
    return calls


def _chat_model(context: AgentContext) -> BaseChatModel:
    return llm.get_chat_model(context.provider, context.model, context.temperature)


async def _invoke_model(
    model: Runnable[Any, AIMessage], messages: Sequence[BaseMessage]
) -> tuple[str, list[dict[str, str]]]:
    """Stream model output as `token` custom events; return (content, tool chunks)."""
    content = ""
    tool_chunks: list[dict[str, str]] = []
    stream = await model.astream_events(messages, version="v3")
    async for event in stream:
        if event["event"] != "on_chat_model_stream":
            continue
        chunk = event["data"]["chunk"]
        text = chunk.content if isinstance(chunk.content, str) else ""
        if text:
            content += text
            get_stream_writer()({"kind": "token", "text": text})
        for piece in getattr(chunk, "tool_call_chunks", None) or []:
            tool_chunks.append(piece)
    return content, tool_chunks


async def chat_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, object]:
    """Plain LLM turn; rag context or textgen template become the system prompt."""
    context = runtime.context
    messages = list(state["messages"])
    system_prompt: str | None = None
    if context.agent_type == "textgen" and context.template_content:
        last_human = next(m for m in reversed(messages) if isinstance(m, HumanMessage))
        system_prompt = context.template_content.replace(
            TEMPLATE_PLACEHOLDER, cast(str, last_human.content)
        )
    elif context.agent_type == "rag" and state["source_chunks"]:
        context_block = "\n\n".join(
            f"[{index}] {source['excerpt']}"
            for index, source in enumerate(state["source_chunks"], start=1)
        )
        system_prompt = f"{RAG_SYSTEM_PROMPT}\n\nContext:\n{context_block}"
    if system_prompt:
        messages = [SystemMessage(content=system_prompt), *messages]
    content, _ = await _invoke_model(_chat_model(context), messages)
    return {"messages": [AIMessage(content=content)]}


async def retrieve_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, object]:
    """RAG retrieval: query FAISS, emit `sources`, stash excerpts in state."""
    context = runtime.context
    last = state["messages"][-1]
    query = cast(str, last.content) if isinstance(last, HumanMessage) else ""
    embeddings = llm.get_embeddings()
    query_vector = await embeddings.aembed_query(query)
    results = vector_store.search(context.user_id, query_vector, RAG_TOP_K)
    if not results:
        raise AppError(
            "No documents are indexed yet. Upload a document first.", "NO_DOCUMENTS"
        )
    sources: list[dict[str, object]] = [
        {
            "document_id": result["document_id"],
            "filename": result["filename"],
            "score": result["score"],
            "excerpt": result["excerpt"],
        }
        for result in results
    ]
    get_stream_writer()({"kind": "sources", "sources": sources})
    return {"source_chunks": sources}


async def agent_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, object]:
    """Agent turn: model with bound tools; returns updates, never mutates state."""
    context = runtime.context
    model = _chat_model(context).bind_tools([search_documents, current_datetime])
    content, tool_chunks = await _invoke_model(model, list(state["messages"]))
    tool_calls = _merge_tool_call_chunks(tool_chunks)
    iterations = state["iterations"] + 1
    keep_going = bool(tool_calls) and iterations < MAX_AGENT_ITERATIONS
    return {
        "messages": [AIMessage(content=content, tool_calls=tool_calls)],
        "iterations": iterations,
        "final": not keep_going,
    }


async def tools_executor(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """Run the last message's tool calls; failures become observations, not crashes."""
    del runtime  # noqa: ARG002 - signature symmetry with sibling nodes
    last = cast(AIMessage, state["messages"][-1])
    tool_messages = []
    for call in last.tool_calls:
        tool = TOOLS.get(call["name"])
        get_stream_writer()({
            "kind": "tool_start", "tool": call["name"], "tool_call_id": call["id"],
        })
        if tool is None:
            result = f"Error: unknown tool '{call['name']}'"
        else:
            try:
                result = await tool.ainvoke(call)
            except Exception as exc:  # noqa: BLE001 - observation goes back to the model
                result = f"Error: {exc}"
        get_stream_writer()({
            "kind": "tool_end", "tool": call["name"], "tool_call_id": call["id"],
        })
        tool_messages.append(
            ToolMessage(content=str(result), tool_call_id=call["id"], name=call["name"])
        )
    return {"messages": tool_messages}