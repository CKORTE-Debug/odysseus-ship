import pytest

from verified_memory.errors import InvalidRecordError
from verified_memory.models import SourceRef


def test_source_ref_can_represent_local_document_evidence():
    ref = SourceRef(
        source_type="local_document",
        source_id="doc-1",
        document_name="Surface_Reinstall_SOP.md",
        document_path="docs/Surface_Reinstall_SOP.md",
        chunk_id="doc-1:chunk:001",
        line_start=10,
        line_end=14,
        quote="Load drivers from USB when Wi-Fi is missing.",
    )

    assert ref.source_type == "local_document"
    assert ref.chunk_id == "doc-1:chunk:001"
    assert ref.line_start == 10
    assert ref.line_end == 14


def test_source_ref_can_represent_web_evidence():
    ref = SourceRef(
        source_type="web_source",
        source_id="ms-doc",
        document_name="Microsoft Learn",
        url="https://learn.microsoft.com/example",
        quote="Official documentation excerpt.",
    )

    assert ref.source_type == "web_source"
    assert ref.url == "https://learn.microsoft.com/example"


def test_web_source_requires_url():
    with pytest.raises(InvalidRecordError, match="web_source SourceRef requires url"):
        SourceRef(source_type="web_source", source_id="missing-url")
