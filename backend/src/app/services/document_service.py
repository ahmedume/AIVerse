# src/app/services/document_service.py
# Purpose: document ingestion pipeline — extract (pypdf for pdf) → split 800/100
#          → embed → per-user FAISS; status lifecycle processing/ready/failed.
# Exports: ALLOWED_EXTENSIONS, validate_upload, upload_path, ingest_document

import json
from io import BytesIO
from pathlib import Path

import anyio
import openai
import structlog
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import llm, vector_store
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models.document_model import Document
from app.repositories import document_repo

logger = structlog.get_logger()
settings = get_settings()

ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".pdf"}
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def validate_upload(filename: str, size_bytes: int) -> None:
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise AppError(
            "Unsupported file type. Allowed: txt, md, json, pdf", "INVALID_FILE_TYPE"
        )
    if size_bytes > settings.MAX_UPLOAD_BYTES:
        raise AppError("File is too large (max 20 MB)", "FILE_TOO_LARGE")


def upload_path(document: Document) -> Path:
    filename = Path(document.filename)
    return (
        settings.data_dir_path
        / "uploads"
        / document.user_id
        / f"{document.id}{filename.suffix.lower()}"
    )


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(data)
    text = data.decode("utf-8", errors="replace")
    if suffix == ".json":
        try:
            return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            return text
    return text


async def ingest_document(
    document_id: str, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        try:
            data = upload_path(document).read_bytes()
            text = await _extract_async(document.filename, data)
            if not text.strip():
                raise AppError("No extractable text found in file", "EXTRACTION_FAILED")
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
            )
            chunks = [chunk for chunk in splitter.split_text(text) if chunk.strip()]
            if not chunks:
                raise AppError("No extractable text found in file", "EXTRACTION_FAILED")
            embeddings = llm.get_embeddings()
            vectors = await embeddings.aembed_documents(chunks)
            vector_store.add_chunks(
                document.user_id,
                [
                    {
                        "document_id": document.id,
                        "filename": document.filename,
                        "text": chunk,
                        "embedding": vector,
                    }
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )
            await document_repo.set_status(
                session, document, status="ready", chunk_count=len(chunks)
            )
            await session.commit()
            logger.info(
                "document.ingested",
                user_id=document.user_id,
                document_id=document.id,
                chunk_count=len(chunks),
            )
        except AppError as exc:
            await document_repo.set_status(
                session, document, status="failed", error=exc.message
            )
            await session.commit()
            logger.warning(
                "document.ingest_rejected",
                user_id=document.user_id,
                document_id=document.id,
                error=exc.message,
            )
        except Exception as exc:
            logger.exception("document.ingest_failed", document_id=document.id)
            if isinstance(exc, openai.OpenAIError):
                error = (
                    "Embedding provider unavailable. Check EMBEDDING_PROVIDER "
                    "and its API key in .env"
                )
            else:
                error = "Ingestion failed"
            await document_repo.set_status(
                session, document, status="failed", error=error
            )
            await session.commit()


async def _extract_async(filename: str, data: bytes) -> str:
    return await anyio.to_thread.run_sync(_extract_text, filename, data)


async def get_session_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=session.bind, class_=AsyncSession, expire_on_commit=False
    )