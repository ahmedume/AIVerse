# src/app/repositories/conversation_repo.py
# Purpose: data access for conversations + messages, always scoped by user_id.
# Exports: get_owned, list_by_user, create, rename, delete, add_message,
#          get_messages, last_user_message, delete_last_assistant

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation_model import Conversation
from app.models.message_model import Message


async def get_by_id(session: AsyncSession, conversation_id: str) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    return result.scalar_one_or_none()


async def get_owned(
    session: AsyncSession, conversation_id: str, user_id: str
) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_by_user(session: AsyncSession, user_id: str) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    return list(result.scalars())


async def create(
    session: AsyncSession,
    user_id: str,
    *,
    title: str,
    agent_type: str,
    provider: str,
    model: str,
) -> Conversation:
    conversation = Conversation(
        user_id=user_id,
        title=title,
        agent_type=agent_type,
        provider=provider,
        model=model,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def rename(session: AsyncSession, conversation: Conversation, title: str) -> None:
    conversation.title = title
    await session.flush()


async def remove(session: AsyncSession, conversation: Conversation) -> None:
    await session.delete(conversation)
    await session.flush()


async def add_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    token_count: int = 0,
) -> Message:
    next_seq = await session.scalar(
        select(func.coalesce(func.max(Message.seq), 0) + 1).where(
            Message.conversation_id == conversation_id
        )
    )
    message = Message(
        conversation_id=conversation_id,
        seq=next_seq or 1,
        role=role,
        content=content,
        token_count=token_count,
    )
    session.add(message)
    await session.flush()
    return message


async def get_messages(session: AsyncSession, conversation_id: str) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq)
    )
    return list(result.scalars())


async def last_user_message(session: AsyncSession, conversation_id: str) -> Message | None:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role == "user")
        .order_by(Message.seq.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def delete_last_assistant(session: AsyncSession, conversation_id: str) -> None:
    await session.execute(
        delete(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
            Message.seq
            == select(func.max(Message.seq))
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "assistant",
            )
            .scalar_subquery(),
        )
    )
    await session.flush()