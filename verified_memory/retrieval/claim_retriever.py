"""Deterministic keyword retrieval over MemoryClaim records."""

from __future__ import annotations

import re
from dataclasses import dataclass

from verified_memory.errors import InvalidRecordError
from verified_memory.models import MemoryClaim

_TERM_RE = re.compile(r"[\w'-]+", re.UNICODE)


@dataclass(frozen=True)
class ClaimRetrievalResult:
    claim: MemoryClaim
    score: int
    matched_terms: list[str]
    reason: str


def retrieve_claims_by_keyword(
    query: str,
    claims: list[MemoryClaim],
    *,
    max_results: int = 5,
    case_sensitive: bool = False,
    include_archived: bool = False,
) -> list[ClaimRetrievalResult]:
    """Rank memory claims using exact phrase, term, and claim-type matches."""

    if not str(query or "").strip():
        raise InvalidRecordError("query must not be empty")
    if max_results < 1:
        raise InvalidRecordError("max_results must be >= 1")

    comparable_query = query if case_sensitive else query.lower()
    query_terms = _terms(query, case_sensitive=case_sensitive)
    results: list[ClaimRetrievalResult] = []

    for claim in claims:
        if claim.status == "archived" and not include_archived:
            continue
        comparable_claim = claim.claim if case_sensitive else claim.claim.lower()
        comparable_type = claim.claim_type if case_sensitive else claim.claim_type.lower()
        score = 0
        reasons: list[str] = []
        matched_terms: list[str] = []

        if comparable_query in comparable_claim:
            score += 3
            reasons.append("exact_phrase")

        for original_term, comparable_term in query_terms:
            if comparable_term in comparable_claim:
                score += 1
                matched_terms.append(original_term)
            if comparable_term in comparable_type:
                score += 1
                reasons.append(f"claim_type:{original_term}")

        if score > 0:
            results.append(
                ClaimRetrievalResult(
                    claim=claim,
                    score=score,
                    matched_terms=_dedupe(matched_terms),
                    reason=", ".join(_dedupe(reasons)) or "term_match",
                )
            )

    results.sort(key=lambda result: (-result.score, result.claim.claim, result.claim.id))
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
