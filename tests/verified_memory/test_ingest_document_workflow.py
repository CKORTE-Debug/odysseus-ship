from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows import ingest_document


def test_ingest_document_stores_chunks(tmp_path):
    path = tmp_path / "guide.txt"
    path.write_text("\n".join(f"line {i}" for i in range(1, 7)), encoding="utf-8")
    store = SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3")

    result = ingest_document(path, store, max_lines=3, overlap_lines=1)

    stored = store.list_document_chunks_by_document_id(result.document_id)
    assert result.document_name == "guide.txt"
    assert result.chunks_created == 3
    assert len(stored) == 3
    assert result.chunk_ids == [chunk.chunk_id for chunk in stored]


def test_ingest_document_replaces_existing_chunks_for_same_document(tmp_path):
    path = tmp_path / "guide.txt"
    path.write_text("one\ntwo\nthree\nfour", encoding="utf-8")
    store = SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3")

    first = ingest_document(path, store, max_lines=2, overlap_lines=0)
    second = ingest_document(path, store, max_lines=2, overlap_lines=0)

    assert second.document_id == first.document_id
    assert second.warnings == ["replaced_existing_chunks:2"]
    assert len(store.list_document_chunks_by_document_id(second.document_id)) == 2
