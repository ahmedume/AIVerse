# src/app/routers/documents_router.py
# Purpose: document upload/list/delete + background ingestion, ownership-scoped.
# Exports: router

from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile

from app.core.config import get_settings
from app.core.database import SessionDep
from app.core.exceptions import NotFoundError
from app.core.rate_limit import limiter, user_key
from app.core.vector_store import remove_document
from app.dependencies import get_current_user
from app.models.user_model import User
from app.repositories import document_repo
from app.schemas.common import Envelope
from app.schemas.document_schema import DocumentOut
from app.services import document_service

settings = get_settings()
logger = structlog.get_logger()

router = APIRouter(tags=["documents"])


@router.post("/documents", status_code=201, response_model=Envelope[DocumentOut])
@limiter.limit(settings.DOCUMENT_RATE_LIMIT, key_func=user_key)
async def upload_document(
    request: Request,
    file: UploadFile,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
) -> Envelope[DocumentOut]:
    filename = Path(file.filename or "upload").name
    data = await file.read()
    document_service.validate_upload(filename, len(data))
    document = await document_repo.create(
        session,
        current_user.id,
        filename=filename,
        content_type=file.content_type or "",
        size_bytes=len(data),
    )
    await session.commit()
    path = document_service.upload_path(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    session_factory = await document_service.get_session_factory(session)
    background_tasks.add_task(
        document_service.ingest_document, document.id, session_factory
    )
    logger.info("document.uploaded", user_id=current_user.id, document_id=document.id)
    return Envelope(data=DocumentOut.model_validate(document))


@router.get("/documents", response_model=Envelope[list[DocumentOut]])
async def list_documents(
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[list[DocumentOut]]:
    documents = await document_repo.list_by_user(session, current_user.id)
    return Envelope(data=[DocumentOut.model_validate(d) for d in documents])


@router.delete("/documents/{document_id}", response_model=Envelope[None])
async def delete_document(
    document_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[None]:
    document = await document_repo.get_owned(session, document_id, current_user.id)
    if document is None:
        raise NotFoundError("Document not found")
    remove_document(current_user.id, document.id)
    document_service.upload_path(document).unlink(missing_ok=True)
    await document_repo.remove(session, document)
    await session.commit()
    logger.info("document.deleted", user_id=current_user.id, document_id=document.id)
    return Envelope(data=None)