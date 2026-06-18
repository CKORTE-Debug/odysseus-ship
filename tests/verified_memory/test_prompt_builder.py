from datetime import datetime, timedelta, timezone

from verified_memory.models import DocumentChunk, MemoryClaim, SourceRef
from verified_memory.prompting import build_verified_memory_prompt
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
    return KeywordRetrievalResult(chunk=chunk, score=4, matched_terms=["Wi-Fi"], reason="term_match")


def _claim(status="verified", *, last_verified_at=None, stale_after_days=60, source_refs=None):
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


def _claim_result(claim):
    return ClaimRetrievalResult(claim=claim, score=5, matched_terms=["Wi-Fi"], reason="term_match")


def _prompt_for_claim(claim):
    package = build_verified_context_package("What does the SOP say about Wi-Fi?", [_chunk_result()], [_claim_result(claim)], now=NOW)
    return build_verified_memory_prompt(package)


def test_prompt_builder_creates_system_and_user_messages():
    prompt = _prompt_for_claim(_claim(last_verified_at=NOW - timedelta(days=1)))

    assert prompt.system_message
    assert prompt.user_message
    assert prompt.messages[0]["role"] == "system"
    assert prompt.messages[1]["role"] == "user"


def test_prompt_includes_original_question():
    prompt = _prompt_for_claim(_claim(last_verified_at=NOW - timedelta(days=1)))

    assert "What does the SOP say about Wi-Fi?" in prompt.user_message


def test_prompt_includes_usable_fresh_verified_claim():
    prompt = _prompt_for_claim(_claim(last_verified_at=NOW - timedelta(days=1)))

    usable = prompt.evidence_blocks["usable_verified_claims"]
    assert usable[0]["claim"] == "Users must connect to Wi-Fi."
    assert usable[0]["usable_evidence"] is True


def test_prompt_labels_unverified_claim_as_not_confirmed():
    prompt = _prompt_for_claim(_claim(status="unverified", source_refs=[_source_ref()]))

    not_confirmed = prompt.evidence_blocks["not_confirmed_claims"]
    assert not_confirmed[0]["reason_not_usable"] == "unverified_claim"
    assert "not confirmed" in prompt.user_message.lower()


def test_prompt_labels_stale_claim_as_not_confirmed():
    prompt = _prompt_for_claim(_claim(last_verified_at=NOW - timedelta(days=61), stale_after_days=60))

    not_confirmed = prompt.evidence_blocks["not_confirmed_claims"]
    assert not_confirmed[0]["reason_not_usable"] == "stale_claim"
    assert not_confirmed[0]["should_verify"] is True


def test_prompt_labels_contradicted_claim_as_not_usable_evidence():
    prompt = _prompt_for_claim(_claim(status="contradicted", source_refs=[_source_ref()]))

    not_confirmed = prompt.evidence_blocks["not_confirmed_claims"]
    assert not_confirmed[0]["reason_not_usable"] == "contradicted_claim"
    assert not_confirmed[0]["usable_evidence"] is False


def test_prompt_includes_retrieved_chunks_with_source_refs():
    prompt = _prompt_for_claim(_claim(last_verified_at=NOW - timedelta(days=1)))

    chunk = prompt.evidence_blocks["local_evidence_chunks"][0]
    assert chunk["chunk_id"] == "doc-1:chunk:0001"
    assert chunk["source_ref"]["line_start"] == 1


def test_prompt_includes_warnings_from_context_package():
    prompt = _prompt_for_claim(_claim(status="unverified", source_refs=[_source_ref()]))

    assert "unverified_claims_retrieved" in prompt.warnings
    assert "unverified_claims_retrieved" in prompt.user_message


def test_prompt_instructs_model_to_cite_only_provided_source_refs():
    prompt = _prompt_for_claim(_claim(last_verified_at=NOW - timedelta(days=1)))

    assert "Only cite source references that appear in the context." in prompt.system_message


def test_prompt_instructs_model_to_say_when_evidence_is_insufficient():
    prompt = _prompt_for_claim(_claim(last_verified_at=NOW - timedelta(days=1)))

    assert "If the evidence is insufficient, say so." in prompt.system_message


def test_prompt_does_not_claim_online_verification_happened():
    prompt = _prompt_for_claim(_claim(last_verified_at=NOW - timedelta(days=1)))

    assert prompt.metadata["online_verification_performed"] is False
    assert "Do not claim that online verification was performed" in prompt.system_message
