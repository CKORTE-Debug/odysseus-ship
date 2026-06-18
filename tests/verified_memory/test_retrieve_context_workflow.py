from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows import ingest_document, retrieve_context


def test_retrieve_context_returns_relevant_chunk(tmp_path):
    path = tmp_path / "teams.md"
    path.write_text("# Teams\nFolder visible by direct link but not Files tab.\n", encoding="utf-8")
    store = SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3")
    ingest_document(path, store)

    package = retrieve_context("Teams direct link", store, max_results=1)

    assert package.question == "Teams direct link"
    assert len(package.retrieved_chunks) == 1
    assert "direct link" in package.retrieved_chunks[0].text


def test_retrieve_context_includes_source_ref(tmp_path):
    path = tmp_path / "teams.txt"
    path.write_text("Microsoft Teams folder note\n", encoding="utf-8")
    store = SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3")
    ingest_document(path, store)

    package = retrieve_context("Teams folder", store, max_results=1)
    source_ref = package.retrieved_chunks[0].source_ref

    assert source_ref.source_type == "local_document"
    assert source_ref.chunk_id == package.retrieved_chunks[0].chunk_id
    assert source_ref.line_start == 1
    assert source_ref.line_end == 1


def test_retrieve_context_does_not_generate_answer(tmp_path):
    path = tmp_path / "teams.txt"
    path.write_text("Microsoft Teams folder note\n", encoding="utf-8")
    store = SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3")
    ingest_document(path, store)

    package = retrieve_context("Teams", store, max_results=1)

    assert package.metadata["answer_generated"] is False
    assert "answer" not in package.to_dict()


def test_retrieve_context_warns_when_no_chunks_match(tmp_path):
    store = SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3")

    package = retrieve_context("Teams", store, max_results=1)

    assert package.retrieved_chunks == []
    assert package.warnings == ["no_relevant_chunks_found"]
