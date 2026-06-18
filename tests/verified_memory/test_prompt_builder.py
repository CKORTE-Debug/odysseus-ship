from datetime import datetime, timezone

from verified_memory.models import SourceRef
from verified_memory.prompting import build_verified_memory_prompt
from verified_memory.retrieval.context_package import RetrievedChunkContext, VerifiedContextPackage
from verified_memory.retrieval.verified_context_builder import RetrievedClaimContext

NOW = datetime(2026, 6, 17, tzinfo=timezone.utc)


def _ref(chunk_id="doc-1:chunk:0001"):
    return SourceRef(
        source_type="local_document",
        source_id="doc-1",
        document_name="sop.md",
        document_path="/tmp/sop.md",
        chunk_id=chunk_id,
        line_start=1,
        line_end=2,
        quote="Users must connect to Wi-Fi.",
    )


def _claim(status="verified", staleness_status="fresh", usable=True, claim_id="claim-1"):
    return RetrievedClaimContext(
        claim_id=claim_id,
        claim="Users must connect to Wi-Fi.",
        claim_type="requirement",
        status=status,
        confidence="high" if usable else "low",
        sensitivity="private",
        staleness_status=staleness_status,
        staleness_reason="test",
        should_verify=not usable,
        score=1,
        matched_terms=["wi-fi"],
        source_refs=[_ref()],
        allowed_web_search=False,
        usable_evidence=usable,
    )


def _chunk():
    ref = _ref("doc-1:chunk:0002")
    return RetrievedChunkContext(
        chunk_id="doc-1:chunk:0002",
        document_name="sop.md",
        document_path="/tmp/sop.md",
        line_start=3,
        line_end=4,
        score=1,
        matched_terms=["wi-fi"],
        text="If Wi-Fi is unavailable, use the approved adapter.",
        source_ref=ref,
    )


def _package(claims=None, chunks=None, warnings=None):
    return VerifiedContextPackage(
        question="What does the SOP say about Wi-Fi?",
        retrieved_chunks=chunks if chunks is not None else [_chunk()],
        retrieved_claims=claims if claims is not None else [_claim()],
        warnings=warnings or ["test_warning"],
        created_at=NOW,
    )


def test_prompt_builder_creates_system_and_user_messages():
    prompt = build_verified_memory_prompt(_package())

    assert prompt.system_message
    assert prompt.user_message
    assert prompt.messages == [
        {"role": "system", "content": prompt.system_message},
        {"role": "user", "content": prompt.user_message},
    ]


def test_prompt_includes_original_question():
    prompt = build_verified_memory_prompt(_package())

    assert "What does the SOP say about Wi-Fi?" in prompt.user_message


def test_prompt_includes_usable_fresh_verified_claim():
    prompt = build_verified_memory_prompt(_package(claims=[_claim()]))

    usable = prompt.evidence_blocks["usable_verified_claims"]
    assert usable[0]["claim_id"] == "claim-1"
    assert usable[0]["status"] == "verified"
    assert usable[0]["staleness_status"] == "fresh"


def test_prompt_labels_unverified_claim_as_not_confirmed():
    prompt = build_verified_memory_prompt(_package(claims=[_claim("unverified", "unverified", False)]))

    block = prompt.evidence_blocks["not_confirmed_claims"][0]
    assert "not confirmed" in prompt.user_message
    assert "unverified claims are leads only" in block["reason_not_usable"]


def test_prompt_labels_stale_claim_as_not_confirmed():
    prompt = build_verified_memory_prompt(_package(claims=[_claim("verified", "stale", False)]))

    block = prompt.evidence_blocks["not_confirmed_claims"][0]
    assert "stale claims are leads only" in block["reason_not_usable"]


def test_prompt_labels_contradicted_claim_as_not_usable_evidence():
    prompt = build_verified_memory_prompt(_package(claims=[_claim("contradicted", "contradicted", False)]))

    block = prompt.evidence_blocks["not_confirmed_claims"][0]
    assert "contradicted claims are not usable evidence" in block["reason_not_usable"]


def test_prompt_includes_retrieved_chunks_with_source_refs():
    prompt = build_verified_memory_prompt(_package())

    chunk = prompt.evidence_blocks["local_evidence_chunks"][0]
    assert chunk["chunk_id"] == "doc-1:chunk:0002"
    assert chunk["source_ref"] == "doc-1:chunk:0002"
    assert "approved adapter" in chunk["text"]


def test_prompt_includes_warnings_from_context_package():
    prompt = build_verified_memory_prompt(_package(warnings=["stale_claims_retrieved"]))

    assert prompt.warnings == ["stale_claims_retrieved"]
    assert "stale_claims_retrieved" in prompt.user_message


def test_prompt_instructs_model_to_cite_only_provided_source_refs():
    prompt = build_verified_memory_prompt(_package())

    assert "Only cite source references that appear in the context" in prompt.system_message
    assert "Do not invent citations" in prompt.system_message


def test_prompt_instructs_model_to_say_when_evidence_is_insufficient():
    prompt = build_verified_memory_prompt(_package())

    assert "If the evidence is insufficient, say so" in prompt.system_message


def test_prompt_does_not_claim_online_verification_happened():
    prompt = build_verified_memory_prompt(_package())

    assert prompt.metadata["online_verification_performed"] is False
    assert "online verification was performed" not in prompt.user_message.lower()
