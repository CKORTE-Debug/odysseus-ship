from verified_memory.models import DocumentChunk
from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows import extract_claims


def _store(tmp_path):
    return SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3")


def _chunk(document_id, chunk_id, text):
    return DocumentChunk(
        document_id=document_id,
        document_name=f"{document_id}.md",
        document_path=f"/tmp/{document_id}.md",
        chunk_id=chunk_id,
        text=text,
        line_start=1,
        line_end=len(text.splitlines()) or 1,
    )


def test_workflow_stores_extracted_claims_in_sqlite(tmp_path):
    store = _store(tmp_path)
    chunk = _chunk("doc-1", "doc-1:chunk:0001", "Users must connect to Wi-Fi.")
    store.add_document_chunk(chunk)

    result = extract_claims(store)

    assert result.claims_created == 1
    loaded = store.get_memory_claim(result.claim_ids[0])
    assert loaded.claim == "Users must connect to Wi-Fi."
    assert loaded.status == "unverified"


def test_workflow_can_extract_for_one_document_id(tmp_path):
    store = _store(tmp_path)
    store.add_document_chunk(_chunk("doc-1", "doc-1:chunk:0001", "Users must connect to Wi-Fi."))
    store.add_document_chunk(_chunk("doc-2", "doc-2:chunk:0001", "Admins should check Teams."))

    result = extract_claims(store, document_id="doc-2")

    assert result.claims_created == 1
    loaded = store.get_memory_claim(result.claim_ids[0])
    assert loaded.claim == "Admins should check Teams."
    assert loaded.metadata["source_document_id"] == "doc-2"


def test_workflow_can_extract_for_specific_chunk_ids(tmp_path):
    store = _store(tmp_path)
    store.add_document_chunk(_chunk("doc-1", "doc-1:chunk:0001", "Users must connect to Wi-Fi."))
    store.add_document_chunk(_chunk("doc-1", "doc-1:chunk:0002", "Admins should check Teams."))

    result = extract_claims(store, chunk_ids=["doc-1:chunk:0002"])

    assert result.claims_created == 1
    assert store.get_memory_claim(result.claim_ids[0]).claim == "Admins should check Teams."


def test_workflow_skips_exact_duplicate_claim_from_same_chunk(tmp_path):
    store = _store(tmp_path)
    chunk = _chunk("doc-1", "doc-1:chunk:0001", "Users must connect to Wi-Fi.")
    store.add_document_chunk(chunk)

    first = extract_claims(store)
    second = extract_claims(store)

    assert first.claims_created == 1
    assert second.claims_created == 0
    assert any(warning.startswith("duplicate_skipped:doc-1:chunk:0001") for warning in second.warnings)


def test_workflow_returns_warning_when_no_claims_found(tmp_path):
    store = _store(tmp_path)
    store.add_document_chunk(_chunk("doc-1", "doc-1:chunk:0001", "Teams is a collaboration app."))

    result = extract_claims(store)

    assert result.claims_created == 0
    assert result.claim_ids == []
    assert "no_claims_extracted" in result.warnings


def test_workflow_preserves_custom_defaults(tmp_path):
    store = _store(tmp_path)
    store.add_document_chunk(_chunk("doc-1", "doc-1:chunk:0001", "Admins should check Teams."))

    result = extract_claims(store, default_sensitivity="public", allowed_web_search=True)

    loaded = store.get_memory_claim(result.claim_ids[0])
    assert loaded.sensitivity == "public"
    assert loaded.allowed_web_search is True
