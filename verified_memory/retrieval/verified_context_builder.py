"""Build deterministic verified context packages from local retrieval results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from verified_memory.models import SourceRef
from verified_memory.models._helpers import datetime_to_json
from verified_memory.retrieval.claim_retriever import ClaimRetrievalResult
from verified_memory.retrieval.context_package import VerifiedContextPackage, build_context_package
from verified_memory.retrieval.keyword_retriever import KeywordRetrievalResult
from verified_memory.verification.staleness import StalenessResult, evaluate_staleness


@dataclass(frozen=True)
class RetrievedClaimContext:
    claim_id: str
    claim: str
    claim_type: str
    status: str
    confidence: str
    sensitivity: str
    staleness_status: str
    staleness_reason: str
    should_verify: bool
    score: int
    matched_terms: list[str]
    source_refs: list[SourceRef]
    allowed_web_search: bool
    usable_evidence: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim": self.claim,
            "claim_type": self.claim_type,
            "status": self.status,
            "confidence": self.confidence,
            "sensitivity": self.sensitivity,
            "staleness_status": self.staleness_status,
            "staleness_reason": self.staleness_reason,
            "should_verify": self.should_verify,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "allowed_web_search": self.allowed_web_search,
            "usable_evidence": self.usable_evidence,
        }


def build_verified_context_package(
    question: str,
    chunk_results: list[KeywordRetrievalResult],
    claim_results: list[ClaimRetrievalResult],
    *,
    now: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> VerifiedContextPackage:
    """Build a source-linked context package with claim safety labels."""

    warnings: list[str] = []
    if not chunk_results:
        warnings.append("no_chunks_found")
    if not claim_results:
        warnings.append("no_claims_found")

    retrieved_claims = []
    for result in claim_results:
        staleness = evaluate_staleness(result.claim, now=now)
        retrieved_claim = _to_retrieved_claim(result, staleness)
        retrieved_claims.append(retrieved_claim)
        _add_claim_warnings(warnings, retrieved_claim)

    package = build_context_package(
        question,
        chunk_results,
        warnings=_dedupe(warnings),
        metadata={
            "answer_generated": False,
            "retrieval_method": "keyword",
            "claim_count": len(retrieved_claims),
            **(metadata or {}),
        },
    )
    return VerifiedContextPackage(
        question=package.question,
        retrieved_chunks=package.retrieved_chunks,
        retrieved_claims=retrieved_claims,
        warnings=package.warnings,
        created_at=package.created_at,
        metadata=package.metadata,
    )


def _to_retrieved_claim(result: ClaimRetrievalResult, staleness: StalenessResult) -> RetrievedClaimContext:
    claim = result.claim
    usable_evidence = (
        claim.status == "verified"
        and staleness.status in {"fresh", "never_stale"}
        and bool(claim.source_refs)
    )
    return RetrievedClaimContext(
        claim_id=claim.id,
        claim=claim.claim,
        claim_type=claim.claim_type,
        status=claim.status,
        confidence=claim.confidence,
        sensitivity=claim.sensitivity,
        staleness_status=staleness.status,
        staleness_reason=staleness.reason,
        should_verify=staleness.should_verify,
        score=result.score,
        matched_terms=list(result.matched_terms),
        source_refs=list(claim.source_refs),
        allowed_web_search=claim.allowed_web_search,
        usable_evidence=usable_evidence,
    )


def _add_claim_warnings(warnings: list[str], claim: RetrievedClaimContext) -> None:
    if claim.staleness_status == "stale":
        warnings.append("stale_claims_retrieved")
    if claim.staleness_status == "unverified" or claim.status == "unverified":
        warnings.append("unverified_claims_retrieved")
    if claim.status == "contradicted" or claim.staleness_status == "contradicted":
        warnings.append("contradicted_claims_retrieved")
    if claim.status == "archived" or claim.staleness_status == "archived":
        warnings.append("archived_claims_included")
    if not claim.source_refs:
        warnings.append("claims_missing_source_refs")


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
