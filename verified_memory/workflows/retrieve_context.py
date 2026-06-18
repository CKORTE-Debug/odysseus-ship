"""Workflow for building a local source-linked context package."""

from __future__ import annotations

from verified_memory.retrieval import VerifiedContextPackage, build_context_package, retrieve_chunks_by_keyword
from verified_memory.storage import SQLiteVerifiedMemoryStore


def retrieve_context(
    question: str,
    store: SQLiteVerifiedMemoryStore,
    *,
    max_results: int = 5,
) -> VerifiedContextPackage:
    """Retrieve local chunks and package them with source references; no answer generation."""

    chunks = store.list_document_chunks()
    results = retrieve_chunks_by_keyword(question, chunks, max_results=max_results)
    warnings = [] if results else ["no_relevant_chunks_found"]
    return build_context_package(
        question,
        results,
        warnings=warnings,
        metadata={"answer_generated": False, "retrieval_method": "keyword"},
    )
