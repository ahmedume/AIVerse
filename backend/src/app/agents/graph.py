# src/app/agents/graph.py
# Purpose: compiled StateGraph routing all four chat modes; node policies.
# Exports: AGENT_GRAPH, RECURSION_LIMIT

from collections.abc import Hashable
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import RetryPolicy, TimeoutPolicy

from app.agents.nodes import agent_node, chat_node, retrieve_node, tools_executor
from app.agents.types import AgentContext, AgentState

RECURSION_LIMIT = 30

_ROUTE_TARGETS: dict[Hashable, str] = {
    "chat": "chat",
    "rag": "retrieve",
    "textgen": "chat",
    "agent": "agent",
}


def _route(state: AgentState, runtime: Runtime[AgentContext]) -> str:
    del state  # noqa: ARG002 - mode lives in runtime context, not state
    return runtime.context.agent_type


def _should_continue(state: AgentState) -> str:
    return "tools" if not state["final"] else "end"


def build_agent_graph() -> Any:
    policy = RetryPolicy(max_attempts=2)
    timeout = TimeoutPolicy(run_timeout=30)
    graph = StateGraph(AgentState, context_schema=AgentContext)
    graph.add_node("chat", chat_node, retry_policy=policy, timeout=timeout)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("agent", agent_node, retry_policy=policy, timeout=timeout)
    graph.add_node("tools", tools_executor)
    graph.add_conditional_edges(START, _route, _ROUTE_TARGETS)
    graph.add_edge("retrieve", "chat")
    graph.add_edge("chat", END)
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")
    return graph.compile()


AGENT_GRAPH = build_agent_graph()