import pytest

from verified_memory.errors import InvalidRecordError
from verified_memory.models import DocumentChunk


def test_document_chunk_stores_stable_chunk_page_and_line_references():
    chunk = DocumentChunk(
        document_id="doc-1",
        document_name="example.md",
        document_path="docs/example.md",
        chunk_id="doc-1:chunk:001",
        text="A source paragraph.",
        page=2,
        line_start=5,
        line_end=7,
        metadata={"content_hash": "abc123"},
    )

    assert chunk.chunk_id == "doc-1:chunk:001"
    assert chunk.page == 2
    assert chunk.line_start == 5
    assert chunk.line_end == 7
    assert chunk.metadata["content_hash"] == "abc123"


def test_document_chunk_rejects_empty_text():
    with pytest.raises(InvalidRecordError, match="text must not be empty"):
        DocumentChunk(
            document_id="doc-1",
            document_name="example.md",
            document_path="docs/example.md",
            chunk_id="doc-1:chunk:001",
            text="",
        )
