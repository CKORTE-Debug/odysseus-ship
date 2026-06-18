"""Deterministic line-based chunking for loaded local documents."""

from __future__ import annotations

import re
from dataclasses import dataclass

from verified_memory.errors import InvalidRecordError
from verified_memory.ingestion.document_loader import LoadedDocument
from verified_memory.models import DocumentChunk

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class ChunkSettings:
    max_lines: int = 40
    overlap_lines: int = 5

    def __post_init__(self) -> None:
        if self.max_lines < 1:
            raise InvalidRecordError("max_lines must be >= 1")
        if self.overlap_lines < 0:
            raise InvalidRecordError("overlap_lines must be >= 0")
        if self.overlap_lines >= self.max_lines:
            raise InvalidRecordError("overlap_lines must be less than max_lines")


def chunk_document(
    document: LoadedDocument,
    *,
    max_lines: int = 40,
    overlap_lines: int = 5,
) -> list[DocumentChunk]:
    """Split a loaded document into stable DocumentChunk records."""

    settings = ChunkSettings(max_lines=max_lines, overlap_lines=overlap_lines)
    lines = document.text.splitlines()
    if not any(line.strip() for line in lines):
        raise InvalidRecordError(f"Document has no non-empty lines: {document.document_path}")

    is_markdown = document.document_name.lower().endswith(".md")
    ranges = _markdown_ranges(lines, settings) if is_markdown else _line_ranges(len(lines), settings)
    chunks: list[DocumentChunk] = []
    for index, (start, end) in enumerate(ranges, start=1):
        chunk_lines = lines[start - 1:end]
        text = "\n".join(chunk_lines).strip()
        if not text:
            continue
        heading = _nearest_heading(lines, start) if is_markdown else None
        metadata = {
            "source_line_count": len(chunk_lines),
            "content_sha256": document.metadata.get("content_sha256"),
        }
        if heading:
            metadata["heading"] = heading
        chunks.append(
            DocumentChunk(
                document_id=document.document_id,
                document_name=document.document_name,
                document_path=document.document_path,
                chunk_id=f"{document.document_id}:chunk:{index:04d}",
                text=text,
                line_start=start,
                line_end=end,
                metadata=metadata,
            )
        )
    return chunks


def _line_ranges(line_count: int, settings: ChunkSettings) -> list[tuple[int, int]]:
    ranges = []
    start = 1
    while start <= line_count:
        end = min(start + settings.max_lines - 1, line_count)
        ranges.append((start, end))
        if end == line_count:
            break
        start = end - settings.overlap_lines + 1
    return ranges


def _markdown_ranges(lines: list[str], settings: ChunkSettings) -> list[tuple[int, int]]:
    heading_starts = [index for index, line in enumerate(lines, start=1) if _HEADING_RE.match(line)]
    if len(heading_starts) <= 1:
        return _line_ranges(len(lines), settings)

    ranges: list[tuple[int, int]] = []
    for pos, start in enumerate(heading_starts):
        section_end = heading_starts[pos + 1] - 1 if pos + 1 < len(heading_starts) else len(lines)
        section_length = section_end - start + 1
        if section_length <= settings.max_lines:
            ranges.append((start, section_end))
        else:
            for offset_start, offset_end in _line_ranges(section_length, settings):
                ranges.append((start + offset_start - 1, start + offset_end - 1))
    if heading_starts[0] > 1:
        ranges.insert(0, (1, heading_starts[0] - 1))
    return ranges


def _nearest_heading(lines: list[str], line_start: int) -> str | None:
    for line in reversed(lines[:line_start]):
        match = _HEADING_RE.match(line)
        if match:
            return match.group(2).strip()
    return None
