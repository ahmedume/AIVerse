# src/app/services/chat_service.py
# Purpose: chat orchestration — conversation resolution, graph-driven SSE streaming
#          (custom events: token / sources / tool_start / tool_end), persistence.
# Exports: chat_events

from collections.abc import AsyncIterator

import structlog
from fastapi import Request
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import AGENT_GRAPH, RECURSION_LIMIT
from app.agents.types import AgentContext
from app.core import vector_store
from app.core.config import get_settings
from app.core.exceptions import AppError, ForbiddenError, ValidationError
from app.models.conversation_model import utcnow
from app.models.template_model import Template
from app.models.user_model import User
from app.repositories import conversation_repo, template_repo, user_repo
from app.schemas.conversation_schema import ChatIn

settings = get_settings()
logger = structlog.get_logger()

AUTO_TITLE_LENGTH = 50
DEFAULT_TEMPERATURE = 0.7


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


async def chat_events(
    request: Request,
    session: AsyncSession,
    user: User,
    payload: ChatIn,
) -> AsyncIterator[tuple[str, object]]:
    """Yield (event_name, data) tuples for the SSE protocol: meta, token, sources,
    tool_start, tool_end, done, error."""

    if not payload.regenerate and not payload.message.strip():
        raise ValidationError("Message is required")

    template: Template | None = None
    if payload.conversation_id:
        conversation = await conversation_repo.get_owned(session, payload.conversation_id, user.id)
        if conversation is None:
            raise ForbiddenError("Conversation not found")
        if conversation.agent_type == "textgen":
            if not payload.template_id:
                raise ValidationError("template_id is required for textgen mode")
            template = await template_repo.get_owned(session, payload.template_id, user.id)
            if template is None:
                raise ForbiddenError("Template not found")
        provider = payload.provider or conversation.provider
        model_name = payload.model or conversation.model
    else:
        provider = payload.provider or settings.DEFAULT_PROVIDER
        model_name = payload.model or settings.DEFAULT_MODEL
        title = (payload.message.strip() or "New conversation")[:AUTO_TITLE_LENGTH]
        conversation = await conversation_repo.create(
            session,
            user.id,
            title=title,
            agent_type="chat",
            provider=provider,
            model=model_name,
        )
        await session.commit()

    if payload.regenerate:
        last_user = await conversation_repo.last_user_message(session, conversation.id)
        if last_user is None:
            raise ValidationError("Nothing to regenerate")
        await conversation_repo.delete_last_assistant(session, conversation.id)
        await session.commit()
        input_message = last_user
    else:
        input_message = await conversation_repo.add_message(
            session, conversation.id, "user", payload.message
        )
        await session.commit()

    history = await conversation_repo.get_messages(session, conversation.id)
    prompt: list[BaseMessage] = []
    for message in history:
        if message.id == input_message.id:
            continue
        if message.role == "user":
            prompt.append(HumanMessage(content=message.content))
        elif message.role == "assistant":
            prompt.append(AIMessage(content=message.content))
    prompt.append(HumanMessage(content=input_message.content))

    if conversation.agent_type == "rag" and not vector_store.has_vectors(user.id):
        raise AppError(
            "No documents are indexed yet. Upload a document first.", "NO_DOCUMENTS"
        )

    yield ("meta", {
        "conversation_id": conversation.id,
        "agent_type": conversation.agent_type,
        "provider": provider,
        "model": model_name,
    })

    user_settings = await user_repo.get_settings(session, user.id)
    context = AgentContext(
        user_id=user.id,
        provider=provider,
        model=model_name,
        agent_type=conversation.agent_type,
        temperature=user_settings.temperature if user_settings else DEFAULT_TEMPERATURE,
        template_content=template.content if template else None,
    )

    content = ""
    try:
        stream = AGENT_GRAPH.astream(
            {"messages": prompt, "iterations": 0, "final": False, "source_chunks": []},
            {"recursion_limit": RECURSION_LIMIT},
            context=context,
            stream_mode="custom",
        )
        async for part in stream:
            kind = part.get("kind")
            if kind == "token":
                text = part["text"]
                content += text
                if await request.is_disconnected():
                    logger.info("chat.aborted", user_id=user.id,
                                conversation_id=conversation.id)
                    return
                yield ("token", {"text": text})
            elif kind == "sources":
                yield ("sources", part["sources"])
            elif kind == "tool_start":
                content = ""
                yield ("tool_start", {
                    "tool": part["tool"],
                    "tool_call_id": part.get("tool_call_id"),
                })
            elif kind == "tool_end":
                yield ("tool_end", {
                    "tool": part["tool"],
                    "tool_call_id": part.get("tool_call_id"),
                })
    except GraphRecursionError:
        logger.warning("chat.agent_loop_limit", user_id=user.id,
                       conversation_id=conversation.id)
        yield ("error", {
            "code": "AGENT_LOOP_LIMIT",
            "message": "The agent hit its loop limit. Try a simpler question.",
        })
        return

    conversation.updated_at = utcnow()
    assistant = await conversation_repo.add_message(
        session, conversation.id, "assistant", content, token_count=_estimate_tokens(content)
    )
    await session.commit()
    logger.info("chat.completed", user_id=user.id, conversation_id=conversation.id,
                token_count=assistant.token_count)
    yield ("done", {"message_id": assistant.id, "token_count": assistant.token_count})