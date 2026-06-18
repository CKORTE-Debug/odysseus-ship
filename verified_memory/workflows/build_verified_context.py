"""Workflow for deterministic local verified-context assembly."""

from __future__ import annotations

from datetime import datetime

from verified_memory.retrieval import VerifiedContextPackage, retrieve_chunks_by_keyword
from verified_memory.retrieval.claim_retriever import retrieve_claims_by_keyword
from verified_memory.retrieval.verified_context_builder import build_verified_context_package
from verified_memory.storage import SQLiteVerifiedMemoryStore


def build_verified_context(
    question: str,
    store: SQLiteVerifiedMemoryStore,
    *,
    max_chunks: int = 5,
    max_claims: int = 5,
    include_archived: bool = False,
    now: datetime | None = None,
) -> VerifiedContextPackage:
    """Assemble local chunks, claims, staleness, warnings, and source refs."""

    chunks = store.list_document_chunks()
    chunk_results = retrieve_chunks_by_keyword(question, chunks, max_results=max_chunks)
    claims = store.list_memory_claims(include_archived=include_archived)
    claim_results = retrieve_claims_by_keyword(
        question,
        claims,
        max_results=max_claims,
        include_archived=include_archived,
    )
    return build_verified_context_package(
        question,
        chunk_results,
        claim_results,
        now=now,
        metadata={"include_archived": include_archived},
    )
