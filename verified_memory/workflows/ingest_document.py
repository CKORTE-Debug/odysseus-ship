"""Workflow for loading, chunking, and storing a local document."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from verified_memory.ingestion import chunk_document, load_document
from verified_memory.storage import SQLiteVerifiedMemoryStore


@dataclass(frozen=True)
class IngestionResult:
    document_id: str
    document_name: str
    chunks_created: int
    chunk_ids: list[str]
    warnings: list[str] = field(default_factory=list)


def ingest_document(
    file_path: str | Path,
    store: SQLiteVerifiedMemoryStore,
    *,
    max_lines: int = 40,
    overlap_lines: int = 5,
    allow_symlinks: bool = False,
    replace_existing: bool = True,
) -> IngestionResult:
    """Load a local document, chunk it, store chunks, and return an audit result."""

    loaded = load_document(file_path, allow_symlinks=allow_symlinks)
    chunks = chunk_document(loaded, max_lines=max_lines, overlap_lines=overlap_lines)
    warnings: list[str] = []
    if replace_existing:
        deleted = store.delete_document_chunks_by_document_id(loaded.document_id)
        if deleted:
            warnings.append(f"replaced_existing_chunks:{deleted}")
    for chunk in chunks:
        store.add_document_chunk(chunk)
    return IngestionResult(
        document_id=loaded.document_id,
        document_name=loaded.document_name,
        chunks_created=len(chunks),
        chunk_ids=[chunk.chunk_id for chunk in chunks],
        warnings=warnings,
    )
