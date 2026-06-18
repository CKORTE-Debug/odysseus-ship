from verified_memory.ingestion import chunk_document, load_document


def test_single_short_file_creates_one_chunk(tmp_path):
    path = tmp_path / "short.txt"
    path.write_text("one\ntwo\nthree", encoding="utf-8")
    document = load_document(path)

    chunks = chunk_document(document, max_lines=40, overlap_lines=5)

    assert len(chunks) == 1
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 3


def test_long_file_creates_multiple_chunks(tmp_path):
    path = tmp_path / "long.txt"
    path.write_text("\n".join(f"line {i}" for i in range(1, 11)), encoding="utf-8")
    document = load_document(path)

    chunks = chunk_document(document, max_lines=4, overlap_lines=1)

    assert len(chunks) == 3
    assert [chunk.line_start for chunk in chunks] == [1, 4, 7]
    assert [chunk.line_end for chunk in chunks] == [4, 7, 10]


def test_overlap_is_applied_correctly(tmp_path):
    path = tmp_path / "overlap.txt"
    path.write_text("\n".join(f"line {i}" for i in range(1, 7)), encoding="utf-8")
    document = load_document(path)

    chunks = chunk_document(document, max_lines=3, overlap_lines=1)

    assert chunks[0].text.splitlines()[-1] == chunks[1].text.splitlines()[0]


def test_chunk_ids_are_stable(tmp_path):
    path = tmp_path / "stable.txt"
    path.write_text("\n".join(f"line {i}" for i in range(1, 7)), encoding="utf-8")
    document = load_document(path)

    first = [chunk.chunk_id for chunk in chunk_document(document, max_lines=3, overlap_lines=1)]
    second = [chunk.chunk_id for chunk in chunk_document(document, max_lines=3, overlap_lines=1)]

    assert first == second
    assert first[0].endswith(":chunk:0001")


def test_empty_chunks_are_not_created(tmp_path):
    path = tmp_path / "spacing.txt"
    path.write_text("first\n\n\nsecond", encoding="utf-8")
    document = load_document(path)

    chunks = chunk_document(document, max_lines=2, overlap_lines=0)

    assert all(chunk.text.strip() for chunk in chunks)


def test_markdown_headings_are_preserved_in_metadata(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text("# Intro\nIntro text\n## Install\nInstall Teams\n", encoding="utf-8")
    document = load_document(path)

    chunks = chunk_document(document, max_lines=10, overlap_lines=1)

    assert chunks[0].metadata["heading"] == "Intro"
    assert chunks[1].metadata["heading"] == "Install"
