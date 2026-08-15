# src/app/services/chat_service.py
# Purpose: chat orchestration — conversation resolution, rag retrieval,
#          textgen template rendering, SSE token streaming (astream_events v3),
#          persistence on done, abort-safe on disconnect.
# Exports: chat_events

from collections.abc import AsyncIterator

import structlog
from fastapi import Request
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm, vector_store
from app.core.config import get_settings
from app.core.exceptions import AppError, ForbiddenError, ValidationError
from app.models.conversation_model import utcnow
from app.models.template_model import Template
from app.models.user_model import User
from app.repositories import conversation_repo, template_repo, user_repo
from app.schemas.conversation_schema import ChatIn
from app.schemas.template_schema import TEMPLATE_PLACEHOLDER

settings = get_settings()
logger = structlog.get_logger()

AUTO_TITLE_LENGTH = 50
DEFAULT_TEMPERATURE = 0.7
RAG_TOP_K = 4
RAG_SYSTEM_PROMPT = (
    "You are Nexus, an assistant that answers using the provided context. "
    "Ground your answer in the context and cite filenames. "
    "If the context does not answer the question, say you don't know."
)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


async def _retrieve(user_id: str, query: str, top_k: int = RAG_TOP_K) -> list[dict[str, object]]:
    embeddings = llm.get_embeddings()
    query_vector = await embeddings.aembed_query(query)
    return vector_store.search(user_id, query_vector, top_k)


async def chat_events(
    request: Request,
    session: AsyncSession,
    user: User,
    payload: ChatIn,
) -> AsyncIterator[tuple[str, object]]:
    """Yield (event_name, data) tuples for the SSE protocol: meta, token, done, error."""

    if not payload.regenerate and not payload.message.strip():
        raise ValidationError("Message is required")

    if payload.conversation_id:
        conversation = await conversation_repo.get_owned(session, payload.conversation_id, user.id)
        if conversation is None:
            raise ForbiddenError("Conversation not found")
        if conversation.agent_type == "agent":
            raise AppError(
                "This conversation mode is not supported yet", "AGENT_TYPE_NOT_SUPPORTED"
            )
        template: Template | None = None
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

    system_prompt: str | None = None
    sources: list[dict[str, object]] = []
    if conversation.agent_type == "rag":
        sources = await _retrieve(user.id, input_message.content)
        if not sources:
            raise AppError(
                "No documents are indexed yet. Upload a document first.", "NO_DOCUMENTS"
            )
        context = "\n\n".join(
            f"[{index}] {source['excerpt']}"
            for index, source in enumerate(sources, start=1)
        )
        system_prompt = f"{RAG_SYSTEM_PROMPT}\n\nContext:\n{context}"
    elif conversation.agent_type == "textgen" and template is not None:
        system_prompt = template.content.replace(
            TEMPLATE_PLACEHOLDER, input_message.content
        )
    if system_prompt is not None:
        prompt.insert(0, SystemMessage(content=system_prompt))

    yield ("meta", {
        "conversation_id": conversation.id,
        "agent_type": conversation.agent_type,
        "provider": provider,
        "model": model_name,
    })
    if sources:
        yield ("sources", sources)

    user_settings = await user_repo.get_settings(session, user.id)
    temperature = user_settings.temperature if user_settings else DEFAULT_TEMPERATURE
    chat_model = llm.get_chat_model(provider, model_name, temperature)

    content = ""
    stream = await chat_model.astream_events(prompt, version="v3")
    async for event in stream:
        if event["event"] != "on_chat_model_stream":
            continue
        chunk = event["data"]["chunk"]
        text = chunk.content if isinstance(chunk.content, str) else ""
        if not text:
            continue
        content += text
        if await request.is_disconnected():
            logger.info("chat.aborted", user_id=user.id, conversation_id=conversation.id)
            return
        yield ("token", {"text": text})

    conversation.updated_at = utcnow()
    assistant = await conversation_repo.add_message(
        session, conversation.id, "assistant", content, token_count=_estimate_tokens(content)
    )
    await session.commit()
    logger.info("chat.completed", user_id=user.id, conversation_id=conversation.id,
                token_count=assistant.token_count)
    yield ("done", {"message_id": assistant.id, "token_count": assistant.token_count})