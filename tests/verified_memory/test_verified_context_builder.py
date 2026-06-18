from datetime import datetime, timedelta, timezone

from verified_memory.models import DocumentChunk, MemoryClaim, SourceRef
from verified_memory.retrieval.claim_retriever import ClaimRetrievalResult
from verified_memory.retrieval.keyword_retriever import KeywordRetrievalResult
from verified_memory.retrieval.verified_context_builder import build_verified_context_package

NOW = datetime(2026, 6, 17, tzinfo=timezone.utc)


def _source_ref():
    return SourceRef(
        source_type="local_document",
        source_id="doc-1",
        document_name="sop.md",
        document_path="/tmp/sop.md",
        chunk_id="doc-1:chunk:0001",
        line_start=1,
        line_end=1,
        quote="Users must connect to Wi-Fi.",
    )


def _claim_result(claim):
    return ClaimRetrievalResult(claim=claim, score=4, matched_terms=["Wi-Fi"], reason="term_match")


def _claim(status="verified", *, source_refs=None, last_verified_at=None, stale_after_days=60):
    if source_refs is None:
        source_refs = [_source_ref()] if status == "verified" else []
    return MemoryClaim(
        claim="Users must connect to Wi-Fi.",
        claim_type="requirement",
        status=status,
        confidence="high" if status == "verified" else "low",
        source_refs=source_refs,
        last_verified_at=last_verified_at,
        stale_after_days=stale_after_days,
    )


def _chunk_result():
    chunk = DocumentChunk(
        document_id="doc-1",
        document_name="sop.md",
        document_path="/tmp/sop.md",
        chunk_id="doc-1:chunk:0001",
        text="Users must connect to Wi-Fi.",
        line_start=1,
        line_end=1,
    )
    return KeywordRetrievalResult(chunk=chunk, score=3, matched_terms=["Wi-Fi"], reason="term_match")


def test_build_context_includes_retrieved_chunks_and_claims():
    claim = _claim(last_verified_at=NOW - timedelta(days=1))

    package = build_verified_context_package("Wi-Fi", [_chunk_result()], [_claim_result(claim)], now=NOW)

    assert len(package.retrieved_chunks) == 1
    assert len(package.retrieved_claims) == 1


def test_fresh_verified_claim_with_source_ref_can_be_usable_evidence():
    claim = _claim(last_verified_at=NOW - timedelta(days=1))

    package = build_verified_context_package("Wi-Fi", [], [_claim_result(claim)], now=NOW)

    assert package.retrieved_claims[0].usable_evidence is True
    assert package.retrieved_claims[0].staleness_status == "fresh"


def test_unverified_claim_is_not_usable_evidence_and_warns():
    claim = _claim(status="unverified")

    package = build_verified_context_package("Wi-Fi", [], [_claim_result(claim)], now=NOW)

    assert package.retrieved_claims[0].usable_evidence is False
    assert "unverified_claims_retrieved" in package.warnings


def test_stale_claim_is_not_usable_evidence_and_should_verify():
    claim = _claim(last_verified_at=NOW - timedelta(days=61), stale_after_days=60)

    package = build_verified_context_package("Wi-Fi", [], [_claim_result(claim)], now=NOW)

    assert package.retrieved_claims[0].usable_evidence is False
    assert package.retrieved_claims[0].should_verify is True
    assert "stale_claims_retrieved" in package.warnings


def test_contradicted_claim_is_not_usable_evidence_and_warns():
    claim = _claim(status="contradicted")

    package = build_verified_context_package("Wi-Fi", [], [_claim_result(claim)], now=NOW)

    assert package.retrieved_claims[0].usable_evidence is False
    assert "contradicted_claims_retrieved" in package.warnings


def test_claim_with_missing_source_refs_is_not_usable_evidence_and_warns():
    claim = _claim(status="unverified", source_refs=[])

    package = build_verified_context_package("Wi-Fi", [], [_claim_result(claim)], now=NOW)

    assert package.retrieved_claims[0].usable_evidence is False
    assert "claims_missing_source_refs" in package.warnings


def test_warnings_when_no_chunks_or_claims_found():
    package = build_verified_context_package("Wi-Fi", [], [], now=NOW)

    assert "no_chunks_found" in package.warnings
    assert "no_claims_found" in package.warnings


def test_retrieved_claims_to_dict_includes_source_refs():
    claim = _claim(last_verified_at=NOW - timedelta(days=1))

    package = build_verified_context_package("Wi-Fi", [], [_claim_result(claim)], now=NOW)
    data = package.to_dict()

    assert data["retrieved_claims"][0]["source_refs"][0]["chunk_id"] == "doc-1:chunk:0001"
