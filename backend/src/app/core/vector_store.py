# src/app/core/vector_store.py
# Purpose: per-user FAISS index on disk (data/vectorstore/{user_id}/) with an
#          in-process cache; rows store their embedding for cheap rebuilds.
# Exports: add_chunks, search, remove_document, has_vectors

import json
from pathlib import Path

import faiss
import numpy as np

from app.core.config import get_settings

settings = get_settings()

_EXCERPT_LENGTH = 300


class _UserIndex:
    def __init__(self, index: faiss.Index, meta: list[dict[str, object]]) -> None:
        self.index = index
        self.meta = meta


_cache: dict[str, _UserIndex] = {}


def _user_dir(user_id: str) -> Path:
    return settings.data_dir_path / "vectorstore" / user_id


def _paths(user_id: str) -> tuple[Path, Path]:
    directory = _user_dir(user_id)
    return directory / "index.faiss", directory / "meta.jsonl"


def _normalize(vector: list[float]) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    return array / norm if norm > 0 else array


def _load(user_id: str) -> _UserIndex:
    cached = _cache.get(user_id)
    if cached is not None:
        return cached
    index_path, meta_path = _paths(user_id)
    if index_path.exists():
        index = faiss.read_index(str(index_path))
        meta: list[dict[str, object]] = []
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                meta.append(json.loads(line))
    else:
        index = faiss.IndexFlatIP(0)
        meta = []
    entry = _UserIndex(index, meta)
    _cache[user_id] = entry
    return entry


def _save(user_id: str, entry: _UserIndex) -> None:
    index_path, meta_path = _paths(user_id)
    directory = index_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    faiss.write_index(entry.index, str(index_path))
    meta_path.write_text(
        "\n".join(json.dumps(row) for row in entry.meta), encoding="utf-8"
    )


def has_vectors(user_id: str) -> bool:
    return _load(user_id).index.ntotal > 0


def add_chunks(user_id: str, chunks: list[dict[str, object]]) -> None:
    if not chunks:
        return
    entry = _load(user_id)
    dim = len(chunks[0]["embedding"])  # type: ignore[arg-type]
    if entry.index.d != dim:
        entry.index = faiss.IndexFlatIP(dim)
        entry.meta = []
    vectors = np.vstack([_normalize(chunk["embedding"]) for chunk in chunks])  # type: ignore[arg-type]
    entry.index.add(vectors)
    entry.meta.extend(
        {
            "document_id": chunk["document_id"],
            "filename": chunk["filename"],
            "text": chunk["text"],
            "embedding": chunk["embedding"],
        }
        for chunk in chunks
    )
    _save(user_id, entry)


def search(
    user_id: str, query_embedding: list[float], top_k: int = 4
) -> list[dict[str, object]]:
    entry = _load(user_id)
    if entry.index.ntotal == 0:
        return []
    query = _normalize(query_embedding).reshape(1, -1)
    scores, ids = entry.index.search(query, min(top_k, entry.index.ntotal))
    results: list[dict[str, object]] = []
    for score, row_id in zip(scores[0], ids[0], strict=True):
        row = entry.meta[int(row_id)]
        text = str(row["text"])
        results.append(
            {
                "document_id": row["document_id"],
                "filename": row["filename"],
                "score": round(float(score), 4),
                "excerpt": text[:_EXCERPT_LENGTH],
                "text": text,
            }
        )
    return results


def remove_document(user_id: str, document_id: str) -> None:
    entry = _load(user_id)
    remaining = [row for row in entry.meta if row["document_id"] != document_id]
    if len(remaining) == len(entry.meta):
        return
    entry.meta = remaining
    if remaining:
        dim = len(remaining[0]["embedding"])  # type: ignore[arg-type]
        entry.index = faiss.IndexFlatIP(dim)
        vectors = np.vstack([_normalize(row["embedding"]) for row in remaining])  # type: ignore[arg-type]
        entry.index.add(vectors)
        _save(user_id, entry)
    else:
        entry.index = faiss.IndexFlatIP(0)
        index_path, meta_path = _paths(user_id)
        index_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)