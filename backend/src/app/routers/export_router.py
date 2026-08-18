# src/app/routers/export_router.py
# Purpose: download endpoint — blocks to DOCX or PDF.
# Exports: router

from fastapi import APIRouter
from fastapi.responses import Response

from app.schemas.detect_schema import DetectSource
from app.schemas.export_schema import ExportRequest
from app.services import export_service, parse_service

router = APIRouter(prefix="/api", tags=["export"])


@router.post("/export")
async def export(request: ExportRequest) -> Response:
    _, blocks = parse_service.resolve_source(request.source.model_dump())
    content, filename = export_service.export_document(blocks, request.format)
    return Response(
        content=content,
        media_type=export_service.MEDIA_TYPES[request.format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )