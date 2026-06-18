"""Source-linked context package structures for future answer generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from verified_memory.models import SourceRef
from verified_memory.models._helpers import datetime_to_json, utc_now
from verified_memory.retrieval.keyword_retriever import KeywordRetrievalResult


@dataclass(frozen=True)
class RetrievedChunkContext:
    chunk_id: str
    document_name: str
    document_path: str
    line_start: int | None
    line_end: int | None
    score: int
    matched_terms: list[str]
    text: str
    source_ref: SourceRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_name": self.document_name,
            "document_path": self.document_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "text": self.text,
            "source_ref": self.source_ref.to_dict(),
        }


@dataclass(frozen=True)
class VerifiedContextPackage:
    question: str
    retrieved_chunks: list[RetrievedChunkContext]
    retrieved_claims: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "retrieved_chunks": [chunk.to_dict() for chunk in self.retrieved_chunks],
            "retrieved_claims": [
                claim.to_dict() if hasattr(claim, "to_dict") else claim
                for claim in self.retrieved_claims
            ],
            "warnings": list(self.warnings),
            "created_at": datetime_to_json(self.created_at),
            "metadata": dict(self.metadata),
        }


def build_context_package(
    question: str,
    retrieval_results: list[KeywordRetrievalResult],
    *,
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> VerifiedContextPackage:
    """Build a source-linked context package without generating an answer."""

    retrieved_chunks = []
    for result in retrieval_results:
        chunk = result.chunk
        source_ref = SourceRef(
            source_type="local_document",
            source_id=chunk.document_id,
            document_name=chunk.document_name,
            document_path=chunk.document_path,
            chunk_id=chunk.chunk_id,
            page=chunk.page,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            quote=chunk.text,
        )
        retrieved_chunks.append(
            RetrievedChunkContext(
                chunk_id=chunk.chunk_id,
                document_name=chunk.document_name,
                document_path=chunk.document_path,
                line_start=chunk.line_start,
                line_end=chunk.line_end,
                score=result.score,
                matched_terms=list(result.matched_terms),
                text=chunk.text,
                source_ref=source_ref,
            )
        )
    return VerifiedContextPackage(
        question=question,
        retrieved_chunks=retrieved_chunks,
        warnings=warnings or [],
        metadata=metadata or {},
    )
