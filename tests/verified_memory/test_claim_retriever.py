from datetime import datetime, timezone

import pytest

from verified_memory.errors import InvalidRecordError
from verified_memory.models import MemoryClaim, SourceRef
from verified_memory.retrieval.claim_retriever import retrieve_claims_by_keyword


def _claim(text, *, status="unverified", claim_type="instruction"):
    refs = []
    if status == "verified":
        refs = [SourceRef(source_type="user_provided", source_id="user-1")]
    return MemoryClaim(
        claim=text,
        claim_type=claim_type,
        status=status,
        source_refs=refs,
        last_verified_at=datetime(2026, 6, 1, tzinfo=timezone.utc) if status == "verified" else None,
        stale_after_days=60 if status == "verified" else None,
    )


def test_claim_retriever_finds_relevant_claim():
    claim = _claim("Users must connect to Wi-Fi during OOBE.")

    results = retrieve_claims_by_keyword("Wi-Fi OOBE", [claim])

    assert len(results) == 1
    assert results[0].claim.id == claim.id


def test_claim_retriever_ranks_exact_phrase_higher():
    exact = _claim("Teams folder visible by direct link")
    terms = _claim("Teams folder permissions")

    results = retrieve_claims_by_keyword("folder visible", [terms, exact])

    assert results[0].claim.id == exact.id
    assert results[0].score > results[1].score


def test_claim_retriever_term_matches_rank_appropriately():
    one = _claim("Intune enrollment is required")
    two = _claim("Intune enrollment Autopilot is required")

    results = retrieve_claims_by_keyword("Intune Autopilot", [one, two])

    assert results[0].claim.id == two.id


def test_claim_retriever_case_insensitive_by_default():
    claim = _claim("microsoft teams folder note")

    results = retrieve_claims_by_keyword("Microsoft Teams", [claim])

    assert len(results) == 1


def test_claim_retriever_empty_query_rejected():
    with pytest.raises(InvalidRecordError, match="query must not be empty"):
        retrieve_claims_by_keyword(" ", [])


def test_claim_retriever_max_results_respected():
    claims = [_claim(f"Teams note {i}") for i in range(5)]

    results = retrieve_claims_by_keyword("Teams", claims, max_results=2)

    assert len(results) == 2


def test_claim_retriever_matched_terms_are_reported():
    claim = _claim("Microsoft Teams folder note")

    results = retrieve_claims_by_keyword("Microsoft folder", [claim])

    assert results[0].matched_terms == ["Microsoft", "folder"]


def test_claim_retriever_ignores_archived_claims_by_default():
    archived = _claim("Teams archived note", status="archived")

    assert retrieve_claims_by_keyword("Teams", [archived]) == []
    assert len(retrieve_claims_by_keyword("Teams", [archived], include_archived=True)) == 1
