import os

import pytest

from verified_memory.errors import InvalidRecordError
from verified_memory.ingestion import load_document


def test_load_txt_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("line one\nline two\n", encoding="utf-8")

    document = load_document(path)

    assert document.document_name == "notes.txt"
    assert document.text == "line one\nline two\n"
    assert document.line_count == 2
    assert document.metadata["extension"] == ".txt"


def test_load_md_file(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text("# Guide\nUse Microsoft Teams.\n", encoding="utf-8")

    document = load_document(path)

    assert document.document_name == "guide.md"
    assert document.line_count == 2


def test_reject_unsupported_extension(tmp_path):
    path = tmp_path / "guide.pdf"
    path.write_text("not really a pdf", encoding="utf-8")

    with pytest.raises(InvalidRecordError, match="Unsupported document extension"):
        load_document(path)


def test_reject_empty_file(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("\n\n", encoding="utf-8")

    with pytest.raises(InvalidRecordError, match="Document is empty"):
        load_document(path)


def test_preserve_document_name_and_path(tmp_path):
    path = tmp_path / "folder" / "doc.txt"
    path.parent.mkdir()
    path.write_text("content", encoding="utf-8")

    document = load_document(path)

    assert document.document_name == "doc.txt"
    assert document.document_path.endswith(os.path.join("folder", "doc.txt"))


def test_count_lines_correctly(tmp_path):
    path = tmp_path / "lines.txt"
    path.write_text("a\nb\nc", encoding="utf-8")

    document = load_document(path)

    assert document.line_count == 3


def test_do_not_follow_symlink_by_default(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("target content", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    with pytest.raises(InvalidRecordError, match="Refusing to follow symlink"):
        load_document(link)
