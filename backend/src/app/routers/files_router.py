# src/app/routers/files_router.py
# Purpose: upload/list/delete document files (parse pipeline entry).
# Exports: router

from fastapi import APIRouter, Request, Response, UploadFile

from app.core.config import get_settings
from app.core.exceptions import FileTooLargeError, ValidationError
from app.schemas.common import Envelope
from app.schemas.file_schema import FileOut
from app.services import parse_service, rag_service

router = APIRouter(prefix="/api/files", tags=["files"])

_MAX_CHUNK = 1024 * 1024


async def _read_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    limit = get_settings().MAX_UPLOAD_BYTES
    while chunk := await file.read(_MAX_CHUNK):
        total += len(chunk)
        if total > limit:
            raise FileTooLargeError(limit // (1024 * 1024))
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=Envelope[FileOut], status_code=201)
async def upload_file(request: Request) -> Envelope[FileOut]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise ValidationError("Multipart field 'file' is required")
        raw = await _read_limited(upload)
        filename = upload.filename or "document.txt"
    else:
        payload = await request.json()
        raw = str(payload.get("text", "")).encode("utf-8")
        filename = payload.get("filename", "document.txt")
    ext, blocks = parse_service.parse_document(raw, filename)
    file_id = parse_service.create_file_id()
    parse_service.save_document(file_id, filename, ext, raw, blocks)
    return Envelope(data=FileOut(**parse_service._file_out(file_id)))


@router.get("", response_model=Envelope[list[FileOut]])
async def list_files() -> Envelope[list[FileOut]]:
    return Envelope(data=[FileOut(**item) for item in parse_service.list_documents()])


@router.delete("/{file_id}", status_code=204)
async def delete_file(file_id: str) -> Response:
    parse_service.delete_document(file_id)
    rag_service.INDEX_CACHE.pop(file_id, None)
    return Response(status_code=204)