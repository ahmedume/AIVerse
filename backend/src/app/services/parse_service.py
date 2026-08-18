# src/app/services/parse_service.py
# Purpose: document intake — bytes -> structured blocks (txt/md/json/pdf/docx),
#          plus atomic per-file storage (original + blocks.json) and list/delete helpers.
# Exports: ALLOWED_EXTS, parse_document, save_document, load_document,
#          list_documents, delete_document

import io
import json
import re
import uuid
from pathlib import Path

import pypdf
from docx import Document

from app.core.blocks import Block
from app.core.config import get_settings
from app.core.exceptions import (
    EmptyDocumentError,
    FileTooLargeError,
    NotFoundError,
    ParseFailedError,
    UnsupportedFileTypeError,
)

ALLOWED_EXTS = {"txt", "md", "json", "pdf", "docx"}
_HEADING_MD = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_MD = re.compile(r"^(?:[-*+]|\d+[.)])\s+(.+)$")
_QUOTE_MD = re.compile(r"^>\s?(.+)$")
_HEADING_FLAT = re.compile(r"^[A-Z0-9][A-Z0-9\s\-—:/()]{4,60}$")
_MANIFEST = "blocks.json"

settings = get_settings()


def _file_ext(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext


def _check_size(raw: bytes) -> None:
    if len(raw) > settings.MAX_UPLOAD_BYTES:
        raise FileTooLargeError(settings.MAX_UPLOAD_BYTES // (1024 * 1024))


def _real_ext(raw: bytes, ext: str) -> str:
    """Content sniffing beats extension: %PDF -> pdf, ZIP -> docx."""
    if ext not in ALLOWED_EXTS:
        raise UnsupportedFileTypeError(ext, ", ".join(sorted(ALLOWED_EXTS)))
    if raw.startswith(b"%PDF"):
        return "pdf"
    if raw[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return "docx"
    if ext == "pdf":
        raise ParseFailedError("Not a valid PDF file")
    if ext == "docx":
        raise ParseFailedError("Not a valid DOCX file")
    if b"\x00" in raw or sum(byte < 9 for byte in raw[:4096]) / max(len(raw[:4096]), 1) > 0.3:
        raise ParseFailedError("File is not UTF-8 text")
    return ext


def _text_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    buffer: list[str] = []
    index = 0

    def flush() -> None:
        nonlocal index
        if buffer:
            blocks.append(Block(index=index, type="paragraph", text=" ".join(buffer)))
            index += 1
            buffer.clear()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            flush()
            continue
        md = _HEADING_MD.match(line)
        if md:
            flush()
            level = len(md.group(1))
            blocks.append(Block(index=index, type="heading", text=md.group(2).strip(), level=level))
            index += 1
            continue
        if _LIST_MD.match(line):
            flush()
            item = _LIST_MD.match(line).group(1).strip()
            blocks.append(Block(index=index, type="list_item", text=item))
            index += 1
            continue
        if _QUOTE_MD.match(line):
            flush()
            quote = _QUOTE_MD.match(line).group(1).strip()
            blocks.append(Block(index=index, type="blockquote", text=quote))
            index += 1
            continue
        if len(line) <= 60 and _HEADING_FLAT.match(line):
            flush()
            blocks.append(Block(index=index, type="heading", text=line, level=1))
            index += 1
            continue
        buffer.append(line)
    flush()
    return blocks


def _parse_docx(raw: bytes) -> list[Block]:
    try:
        doc = Document(io.BytesIO(raw))
    except Exception as err:
        raise ParseFailedError("Could not open the DOCX file") from err
    blocks: list[Block] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        if style.startswith("Heading"):
            level = int(style.replace("Heading", "").strip() or "1")
            blocks.append(Block(index=len(blocks), type="heading", text=text, level=level))
        elif style.startswith("List"):
            blocks.append(Block(index=len(blocks), type="list_item", text=text))
        else:
            blocks.append(Block(index=len(blocks), type="paragraph", text=text))
    return blocks


def _parse_pdf(raw: bytes) -> list[Block]:
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as err:
        raise ParseFailedError("Could not extract text from the PDF") from err
    return _text_blocks(text)


def parse_document(raw: bytes, filename: str) -> tuple[str, list[Block]]:
    """Validate, sniff, and parse file bytes into structural blocks. Returns (ext, blocks)."""
    _check_size(raw)
    ext = _real_ext(raw, _file_ext(filename))
    if ext in ("txt", "md", "json"):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ParseFailedError("File is not valid UTF-8 text") from None
        if ext == "json":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                raise ParseFailedError("Invalid JSON content") from None
            if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                text = "\n\n".join(parsed)
        blocks = _text_blocks(text)
    elif ext == "docx":
        blocks = _parse_docx(raw)
    else:
        blocks = _parse_pdf(raw)
    if not blocks:
        raise EmptyDocumentError()
    return ext, blocks


_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def _dir_for(file_id: str) -> Path:
    if not _ID_RE.match(file_id):
        raise NotFoundError(f"File '{file_id}' not found")
    return settings.uploads_dir / file_id


def save_document(file_id: str, filename: str, ext: str, raw: bytes, blocks: list[Block]) -> None:
    """Persist original bytes + blocks manifest atomically under data/uploads/{file_id}/."""
    folder = _dir_for(file_id)
    folder.mkdir(parents=True, exist_ok=True)
    original = folder / f"original.{ext}"
    original.write_bytes(raw)
    tmp = folder / f"{_MANIFEST}.tmp"
    tmp.write_text(
        json.dumps(
            {"filename": filename, "ext": ext, "blocks": [b.model_dump() for b in blocks]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(folder / _MANIFEST)


def load_document(file_id: str) -> tuple[str, list[Block]]:
    manifest = _dir_for(file_id) / _MANIFEST
    if not manifest.exists():
        raise NotFoundError(f"File '{file_id}' not found")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    blocks = [Block(**b) for b in data["blocks"]]
    return data["filename"], blocks


def _file_out(file_id: str) -> dict:
    manifest = _dir_for(file_id) / _MANIFEST
    if not manifest.exists():
        raise NotFoundError(f"File '{file_id}' not found")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    words = sum(len(b["text"].split()) for b in data["blocks"])
    return {
        "id": file_id,
        "filename": data["filename"],
        "size": (settings.uploads_dir / file_id / f"original.{data['ext']}").stat().st_size,
        "blocks": len(data["blocks"]),
        "words": words,
        "created_at": manifest.stat().st_mtime,
    }


def list_documents() -> list[dict]:
    if not settings.uploads_dir.exists():
        return []
    return [_file_out(folder.name) for folder in sorted(settings.uploads_dir.iterdir())]


def delete_document(file_id: str) -> None:
    folder = _dir_for(file_id)
    if not folder.exists():
        raise NotFoundError(f"File '{file_id}' not found")
    for entry in folder.iterdir():
        entry.unlink(missing_ok=True)
    folder.rmdir()


def resolve_source(source: dict) -> tuple[str, list[Block]]:
    """Resolve {file_id} | {text} source into (name, blocks); text via empty-doc check."""
    if source.get("file_id"):
        return load_document(source["file_id"])
    text = source.get("text") or ""
    if not text.strip():
        raise EmptyDocumentError()
    return "text", _text_blocks(text)


def create_file_id() -> str:
    return uuid.uuid4().hex[:16]
