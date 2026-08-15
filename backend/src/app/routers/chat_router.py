# src/app/routers/chat_router.py
# Purpose: conversation CRUD + SSE chat streaming, ownership-scoped.
# Exports: router

import json
from collections.abc import AsyncIterator

import openai
import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.database import SessionDep
from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.core.rate_limit import limiter, user_key
from app.dependencies import get_current_user
from app.models.conversation_model import Conversation
from app.models.user_model import User
from app.repositories import conversation_repo
from app.schemas.common import Envelope
from app.schemas.conversation_schema import (
    ChatIn,
    ConversationCreateIn,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdateIn,
    MessageOut,
)
from app.services import chat_service

settings = get_settings()
logger = structlog.get_logger()

router = APIRouter(tags=["conversations"])


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _conversation_out(
    conversation: Conversation, message_count: int | None = None
) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        agent_type=conversation.agent_type,
        provider=conversation.provider,
        model=conversation.model,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(conversation.messages) if message_count is None else message_count,
    )


@router.get("/conversations", response_model=Envelope[list[ConversationOut]])
async def list_conversations(
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[list[ConversationOut]]:
    conversations = await conversation_repo.list_by_user(session, current_user.id)
    return Envelope(data=[_conversation_out(c) for c in conversations])


@router.post("/conversations", status_code=201, response_model=Envelope[ConversationOut])
async def create_conversation(
    payload: ConversationCreateIn,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[ConversationOut]:
    conversation = await conversation_repo.create(
        session,
        current_user.id,
        title=payload.title or "New conversation",
        agent_type=payload.agent_type,
        provider=payload.provider or settings.DEFAULT_PROVIDER,
        model=payload.model or settings.DEFAULT_MODEL,
    )
    await session.commit()
    await session.refresh(conversation)
    return Envelope(data=_conversation_out(conversation, message_count=0))


@router.get("/conversations/{conversation_id}", response_model=Envelope[ConversationDetailOut])
async def get_conversation(
    conversation_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[ConversationDetailOut]:
    conversation = await conversation_repo.get_by_id(session, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    if conversation.user_id != current_user.id:
        raise ForbiddenError("Conversation not found")
    return Envelope(
        data=ConversationDetailOut(
            conversation=_conversation_out(conversation),
            messages=[MessageOut.model_validate(m) for m in conversation.messages],
        )
    )


@router.get("/conversations/{conversation_id}/messages",
            response_model=Envelope[list[MessageOut]])
async def get_messages(
    conversation_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[list[MessageOut]]:
    conversation = await conversation_repo.get_by_id(session, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    if conversation.user_id != current_user.id:
        raise ForbiddenError("Conversation not found")
    messages = await conversation_repo.get_messages(session, conversation_id)
    return Envelope(data=[MessageOut.model_validate(m) for m in messages])


@router.patch("/conversations/{conversation_id}", response_model=Envelope[ConversationOut])
async def rename_conversation(
    conversation_id: str,
    payload: ConversationUpdateIn,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[ConversationOut]:
    conversation = await conversation_repo.get_by_id(session, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    if conversation.user_id != current_user.id:
        raise ForbiddenError("Conversation not found")
    await conversation_repo.rename(session, conversation, payload.title)
    await session.commit()
    await session.refresh(conversation)
    return Envelope(data=_conversation_out(conversation))


@router.delete("/conversations/{conversation_id}", response_model=Envelope[None])
async def delete_conversation(
    conversation_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[None]:
    conversation = await conversation_repo.get_by_id(session, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    if conversation.user_id != current_user.id:
        raise ForbiddenError("Conversation not found")
    await conversation_repo.remove(session, conversation)
    await session.commit()
    logger.info("conversation.deleted", user_id=current_user.id, conversation_id=conversation_id)
    return Envelope(data=None)


@router.post("/chat")
@limiter.limit(settings.CHAT_RATE_LIMIT, key_func=user_key)
async def chat(
    request: Request,
    payload: ChatIn,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        try:
            async for name, data in chat_service.chat_events(
                request, session, current_user, payload
            ):
                yield _sse(name, data)
        except AppError as exc:
            logger.warning("chat.error", user_id=current_user.id, code=exc.code)
            yield _sse("error", {"code": exc.code, "message": exc.message})
        except openai.RateLimitError:
            logger.warning("chat.model_rate_limited", user_id=current_user.id)
            yield _sse("error", {
                "code": "MODEL_RATE_LIMITED",
                "message": "The AI provider is rate-limited right now. "
                "Wait a moment and try again.",
            })
        except Exception:
            logger.exception("chat.stream_failed", user_id=current_user.id)
            yield _sse("error", {"code": "INTERNAL_ERROR",
                                 "message": "Something went wrong. Try again."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
