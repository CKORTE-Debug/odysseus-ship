"""Workflow for deterministic claim extraction from stored document chunks."""

from __future__ import annotations

from dataclasses import dataclass, field

from verified_memory.ingestion.claim_extractor import extract_claims_from_chunk, normalize_claim_text
from verified_memory.models import DocumentChunk, MemoryClaim
from verified_memory.storage import SQLiteVerifiedMemoryStore


@dataclass(frozen=True)
class ClaimExtractionResult:
    claims_created: int
    claim_ids: list[str]
    chunks_processed: int
    warnings: list[str] = field(default_factory=list)


def extract_claims(
    store: SQLiteVerifiedMemoryStore,
    *,
    document_id: str | None = None,
    chunk_ids: list[str] | None = None,
    default_sensitivity: str = "private",
    allowed_web_search: bool = False,
) -> ClaimExtractionResult:
    """Extract candidate claims from selected stored chunks and persist them."""

    chunks = _load_chunks(store, document_id=document_id, chunk_ids=chunk_ids)
    warnings: list[str] = []
    claim_ids: list[str] = []
    for chunk in chunks:
        existing_keys = _claim_keys(store.list_memory_claims_by_source_chunk(chunk.chunk_id))
        extracted = extract_claims_from_chunk(
            chunk,
            default_sensitivity=default_sensitivity,
            allowed_web_search=allowed_web_search,
        )
        for claim in extracted:
            key = _claim_key(claim)
            if key in existing_keys:
                warnings.append(f"duplicate_skipped:{chunk.chunk_id}:{normalize_claim_text(claim.claim)}")
                continue
            store.add_memory_claim(claim)
            existing_keys.add(key)
            claim_ids.append(claim.id)

    if not claim_ids:
        warnings.append("no_claims_extracted")
    return ClaimExtractionResult(
        claims_created=len(claim_ids),
        claim_ids=claim_ids,
        chunks_processed=len(chunks),
        warnings=warnings,
    )


def _load_chunks(
    store: SQLiteVerifiedMemoryStore,
    *,
    document_id: str | None,
    chunk_ids: list[str] | None,
) -> list[DocumentChunk]:
    if chunk_ids:
        return [store.get_document_chunk(chunk_id) for chunk_id in chunk_ids]
    if document_id:
        return store.list_document_chunks_by_document_id(document_id)
    return store.list_document_chunks()


def _claim_keys(claims: list[MemoryClaim]) -> set[tuple[str, str]]:
    return {_claim_key(claim) for claim in claims}


def _claim_key(claim: MemoryClaim) -> tuple[str, str]:
    chunk_id = claim.source_refs[0].chunk_id if claim.source_refs else ""
    return (normalize_claim_text(claim.claim), chunk_id or "")
