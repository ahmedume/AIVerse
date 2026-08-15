# src/app/repositories/document_repo.py
# Purpose: data access for documents, always scoped by user_id.
# Exports: create, list_by_user, get_owned, set_status, remove

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_model import Document


async def create(
    session: AsyncSession,
    user_id: str,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
) -> Document:
    document = Document(
        user_id=user_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    session.add(document)
    await session.flush()
    return document


async def list_by_user(session: AsyncSession, user_id: str) -> list[Document]:
    result = await session.execute(
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    return list(result.scalars())


async def get_owned(
    session: AsyncSession, document_id: str, user_id: str
) -> Document | None:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def set_status(
    session: AsyncSession,
    document: Document,
    *,
    status: str,
    error: str | None = None,
    chunk_count: int | None = None,
) -> None:
    document.status = status
    document.error = error
    if chunk_count is not None:
        document.chunk_count = chunk_count
    await session.flush()


async def remove(session: AsyncSession, document: Document) -> None:
    await session.delete(document)
    await session.flush()