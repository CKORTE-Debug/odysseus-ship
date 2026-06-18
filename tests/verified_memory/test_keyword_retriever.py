import pytest

from verified_memory.errors import InvalidRecordError
from verified_memory.models import DocumentChunk
from verified_memory.retrieval import retrieve_chunks_by_keyword


def _chunk(chunk_id, text, heading=None):
    metadata = {"heading": heading} if heading else {}
    return DocumentChunk(
        document_id="doc",
        document_name="doc.txt",
        document_path="/tmp/doc.txt",
        chunk_id=chunk_id,
        text=text,
        line_start=1,
        line_end=1,
        metadata=metadata,
    )


def test_exact_phrase_ranks_higher():
    phrase = _chunk("doc:chunk:0001", "Microsoft Teams hidden folder direct link")
    terms = _chunk("doc:chunk:0002", "Microsoft Teams permissions")

    results = retrieve_chunks_by_keyword("Teams hidden folder", [terms, phrase])

    assert results[0].chunk.chunk_id == "doc:chunk:0001"
    assert results[0].score > results[1].score


def test_term_matches_rank_appropriately():
    one = _chunk("doc:chunk:0001", "Intune enrollment")
    two = _chunk("doc:chunk:0002", "Intune enrollment Autopilot")

    results = retrieve_chunks_by_keyword("Intune Autopilot", [one, two])

    assert results[0].chunk.chunk_id == "doc:chunk:0002"
    assert results[0].score > results[1].score


def test_case_insensitive_by_default():
    chunk = _chunk("doc:chunk:0001", "microsoft teams")

    results = retrieve_chunks_by_keyword("Microsoft Teams", [chunk])

    assert len(results) == 1


def test_empty_query_rejected():
    with pytest.raises(InvalidRecordError, match="query must not be empty"):
        retrieve_chunks_by_keyword(" ", [])


def test_max_results_respected():
    chunks = [_chunk(f"doc:chunk:{i:04d}", "Teams") for i in range(5)]

    results = retrieve_chunks_by_keyword("Teams", chunks, max_results=2)

    assert len(results) == 2


def test_matched_terms_are_reported():
    chunk = _chunk("doc:chunk:0001", "Microsoft Teams folder")

    results = retrieve_chunks_by_keyword("Microsoft folder", [chunk])

    assert results[0].matched_terms == ["Microsoft", "folder"]


def test_heading_metadata_bonus():
    with_heading = _chunk("doc:chunk:0001", "Install instructions Teams", heading="Microsoft Teams")
    without_heading = _chunk("doc:chunk:0002", "Install instructions Teams")

    results = retrieve_chunks_by_keyword("Teams", [without_heading, with_heading])

    assert results[0].chunk.chunk_id == "doc:chunk:0001"
