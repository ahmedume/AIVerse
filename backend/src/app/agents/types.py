# src/app/agents/types.py
# Purpose: LangGraph state + runtime context for all chat modes.
# Exports: AgentState, AgentContext

from langgraph.graph.message import MessagesState
from pydantic import BaseModel


class AgentState(MessagesState):
    """Shared graph state. Model/provider live in AgentContext, never here."""

    iterations: int
    final: bool
    source_chunks: list[dict[str, object]]


class AgentContext(BaseModel):
    """Runtime context injected per run via `context_schema`."""

    user_id: str
    provider: str
    model: str
    agent_type: str
    temperature: float = 0.7
    template_content: str | None = None