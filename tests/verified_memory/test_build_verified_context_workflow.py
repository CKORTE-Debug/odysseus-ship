from datetime import datetime, timedelta, timezone

from verified_memory.models import DocumentChunk, MemoryClaim, SourceRef
from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows import build_verified_context

NOW = datetime(2026, 6, 17, tzinfo=timezone.utc)


def _store(tmp_path):
    return SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3")


def _chunk(text="Users must connect to Wi-Fi."):
    return DocumentChunk(
        document_id="doc-1",
        document_name="sop.md",
        document_path="/tmp/sop.md",
        chunk_id="doc-1:chunk:0001",
        text=text,
        line_start=1,
        line_end=1,
    )


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


def _verified_claim(status="verified", *, last_verified_at=None, stale_after_days=60, source_refs=None):
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


def test_workflow_includes_retrieved_chunks_and_claims(tmp_path):
    store = _store(tmp_path)
    store.add_document_chunk(_chunk())
    claim = _verified_claim(last_verified_at=NOW - timedelta(days=1))
    store.add_memory_claim(claim)

    package = build_verified_context("Wi-Fi", store, now=NOW)

    assert len(package.retrieved_chunks) == 1
    assert len(package.retrieved_claims) == 1


def test_workflow_fresh_verified_claim_can_be_usable_evidence(tmp_path):
    store = _store(tmp_path)
    claim = _verified_claim(last_verified_at=NOW - timedelta(days=1))
    store.add_memory_claim(claim)

    package = build_verified_context("Wi-Fi", store, now=NOW)

    assert package.retrieved_claims[0].usable_evidence is True


def test_workflow_stale_claim_not_usable_and_should_verify(tmp_path):
    store = _store(tmp_path)
    claim = _verified_claim(last_verified_at=NOW - timedelta(days=61), stale_after_days=60)
    store.add_memory_claim(claim)

    package = build_verified_context("Wi-Fi", store, now=NOW)

    assert package.retrieved_claims[0].usable_evidence is False
    assert package.retrieved_claims[0].should_verify is True
    assert "stale_claims_retrieved" in package.warnings


def test_workflow_does_not_mutate_stored_claim_status(tmp_path):
    store = _store(tmp_path)
    claim = _verified_claim(last_verified_at=NOW - timedelta(days=61), stale_after_days=60)
    store.add_memory_claim(claim)

    build_verified_context("Wi-Fi", store, now=NOW)

    assert store.get_memory_claim(claim.id).status == "verified"


def test_workflow_returns_source_refs_for_citeability(tmp_path):
    store = _store(tmp_path)
    claim = _verified_claim(last_verified_at=NOW - timedelta(days=1))
    store.add_memory_claim(claim)

    package = build_verified_context("Wi-Fi", store, now=NOW)

    assert package.retrieved_claims[0].source_refs[0].chunk_id == "doc-1:chunk:0001"


def test_workflow_warns_when_no_chunks_or_claims(tmp_path):
    store = _store(tmp_path)

    package = build_verified_context("Wi-Fi", store, now=NOW)

    assert "no_chunks_found" in package.warnings
    assert "no_claims_found" in package.warnings
