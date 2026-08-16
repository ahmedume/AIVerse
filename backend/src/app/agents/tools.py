# src/app/agents/tools.py
# Purpose: tools exposed to the agent loop.
# Exports: current_datetime, search_documents

from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.runtime import get_runtime

from app.agents.types import AgentContext
from app.core import llm, vector_store

TOOL_TOP_K = 3


@tool
def current_datetime() -> str:
    """Return the current UTC date and time."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


@tool
async def search_documents(query: str, config: RunnableConfig) -> str:
    """Search the user's indexed documents and return the top excerpts."""
    del config  # noqa: ARG002 - config is injected by langchain for runtime access
    context = get_runtime(AgentContext).context
    embeddings = llm.get_embeddings()
    query_vector = await embeddings.aembed_query(query)
    results = vector_store.search(context.user_id, query_vector, TOOL_TOP_K)
    if not results:
        return "No matching documents were found in the user's library."
    return "\n\n".join(
        f"[{index}] {result['excerpt']}"
        for index, result in enumerate(results, start=1)
    )