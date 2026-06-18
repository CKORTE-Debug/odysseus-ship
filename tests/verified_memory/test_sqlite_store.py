from verified_memory.models import ConflictRecord, DocumentChunk, MemoryClaim, SourceRef, VerificationRun
from verified_memory.storage import SQLiteVerifiedMemoryStore


def _store(tmp_path):
    return SQLiteVerifiedMemoryStore(tmp_path / "verified_memory.sqlite3")


def _verified_claim():
    source = SourceRef(
        source_type="local_document",
        source_id="doc-1",
        document_name="example.md",
        document_path="docs/example.md",
        chunk_id="doc-1:chunk:001",
        line_start=1,
        line_end=3,
        quote="Evidence quote.",
    )
    return MemoryClaim(
        claim="A source-linked claim.",
        claim_type="software_behavior",
        source_refs=[source],
        status="verified",
        confidence="high",
        sensitivity="public",
        allowed_web_search=True,
        metadata={"domain": "it_software", "future_key": {"kept": True}},
    )


def test_sqlite_store_can_save_and_load_memory_claim_with_source_refs_intact(tmp_path):
    store = _store(tmp_path)
    claim = _verified_claim()

    store.add_memory_claim(claim)
    loaded = store.get_memory_claim(claim.id)

    assert loaded.to_dict() == claim.to_dict()
    assert loaded.source_refs[0].chunk_id == "doc-1:chunk:001"
    assert loaded.metadata["future_key"] == {"kept": True}


def test_sqlite_store_can_update_memory_claim_status(tmp_path):
    store = _store(tmp_path)
    claim = MemoryClaim(claim="An unverified claim.", claim_type="software_behavior")
    store.add_memory_claim(claim)

    claim.status = "stale"
    store.update_memory_claim(claim)

    assert store.get_memory_claim(claim.id).status == "stale"


def test_sqlite_store_can_archive_claim(tmp_path):
    store = _store(tmp_path)
    claim = MemoryClaim(claim="Claim to archive.", claim_type="software_behavior")
    store.add_memory_claim(claim)

    archived = store.archive_memory_claim(claim.id)

    assert archived.status == "archived"
    assert store.get_memory_claim(claim.id).status == "archived"
    assert store.list_memory_claims(include_archived=False) == []


def test_sqlite_store_can_save_and_retrieve_document_chunk(tmp_path):
    store = _store(tmp_path)
    chunk = DocumentChunk(
        document_id="doc-1",
        document_name="example.md",
        document_path="docs/example.md",
        chunk_id="doc-1:chunk:001",
        text="Original chunk text.",
        line_start=1,
        line_end=2,
    )

    store.add_document_chunk(chunk)
    loaded = store.get_document_chunk(chunk.chunk_id)

    assert loaded.to_dict() == chunk.to_dict()
    assert store.list_document_chunks("doc-1")[0].chunk_id == chunk.chunk_id


def test_sqlite_store_can_save_and_retrieve_conflict_record(tmp_path):
    store = _store(tmp_path)
    conflict = ConflictRecord(
        claim_id="claim-1",
        conflicting_claim_id="claim-2",
        conflict_type="contradiction",
        description="Claims conflict.",
    )

    store.add_conflict_record(conflict)
    loaded = store.get_conflict_record(conflict.id)

    assert loaded.to_dict() == conflict.to_dict()
    assert store.list_conflicts_for_claim("claim-2")[0].id == conflict.id


def test_sqlite_store_can_save_and_retrieve_verification_run(tmp_path):
    store = _store(tmp_path)
    run = VerificationRun(
        claim_id="claim-1",
        status="pending",
        verification_method="local_only",
        sources_checked=[{"source_ref_id": "source-1"}],
        metadata={"note": "no network"},
    )

    store.add_verification_run(run)
    loaded = store.get_verification_run(run.id)

    assert loaded.to_dict() == run.to_dict()
    assert store.list_verification_runs_for_claim("claim-1")[0].id == run.id
