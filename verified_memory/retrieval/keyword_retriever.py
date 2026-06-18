"""Deterministic keyword retrieval over stored DocumentChunk records."""

from __future__ import annotations

import re
from dataclasses import dataclass

from verified_memory.errors import InvalidRecordError
from verified_memory.models import DocumentChunk

_TERM_RE = re.compile(r"[\w'-]+", re.UNICODE)


@dataclass(frozen=True)
class KeywordRetrievalResult:
    chunk: DocumentChunk
    score: int
    matched_terms: list[str]
    reason: str


def retrieve_chunks_by_keyword(
    query: str,
    chunks: list[DocumentChunk],
    *,
    max_results: int = 5,
    case_sensitive: bool = False,
) -> list[KeywordRetrievalResult]:
    """Rank document chunks using exact phrase and term matches."""

    if not str(query or "").strip():
        raise InvalidRecordError("query must not be empty")
    if max_results < 1:
        raise InvalidRecordError("max_results must be >= 1")

    comparable_query = query if case_sensitive else query.lower()
    query_terms = _terms(query, case_sensitive=case_sensitive)
    results: list[KeywordRetrievalResult] = []

    for chunk in chunks:
        comparable_text = chunk.text if case_sensitive else chunk.text.lower()
        heading = str(chunk.metadata.get("heading") or "")
        comparable_heading = heading if case_sensitive else heading.lower()
        score = 0
        reasons: list[str] = []
        matched_terms: list[str] = []

        if comparable_query in comparable_text:
            score += 3
            reasons.append("exact_phrase")

        for original_term, comparable_term in query_terms:
            if comparable_term in comparable_text:
                score += 1
                matched_terms.append(original_term)
            if comparable_heading and comparable_term in comparable_heading:
                score += 1
                reasons.append(f"heading:{original_term}")

        if score > 0:
            results.append(
                KeywordRetrievalResult(
                    chunk=chunk,
                    score=score,
                    matched_terms=_dedupe(matched_terms),
                    reason=", ".join(_dedupe(reasons)) or "term_match",
                )
            )

    results.sort(key=lambda result: (-result.score, result.chunk.document_name, result.chunk.line_start or 0, result.chunk.chunk_id))
    return results[:max_results]


def _terms(query: str, *, case_sensitive: bool) -> list[tuple[str, str]]:
    terms = _dedupe(_TERM_RE.findall(query))
    if case_sensitive:
        return [(term, term) for term in terms]
    return [(term, term.lower()) for term in terms]


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
