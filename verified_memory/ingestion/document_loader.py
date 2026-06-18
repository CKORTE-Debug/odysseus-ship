"""Local Markdown/plain-text document loading for verified memory."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from verified_memory.errors import InvalidRecordError
from verified_memory.models._helpers import datetime_to_json, utc_now

SUPPORTED_EXTENSIONS = {".md", ".txt"}


@dataclass(frozen=True)
class LoadedDocument:
    document_id: str
    document_name: str
    document_path: str
    text: str
    line_count: int
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "document_path": self.document_path,
            "text": self.text,
            "line_count": self.line_count,
            "created_at": datetime_to_json(self.created_at),
            "metadata": dict(self.metadata),
        }


def load_document(file_path: str | Path, *, allow_symlinks: bool = False) -> LoadedDocument:
    """Load a local UTF-8 .md or .txt document without following symlinks by default."""

    path = Path(file_path)
    if path.is_symlink() and not allow_symlinks:
        raise InvalidRecordError(f"Refusing to follow symlink document path: {path}")
    if not path.exists():
        raise InvalidRecordError(f"Document path does not exist: {path}")
    if not path.is_file():
        raise InvalidRecordError(f"Document path is not a file: {path}")
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise InvalidRecordError(
            f"Unsupported document extension {extension!r}; supported extensions are .md and .txt"
        )

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise InvalidRecordError(f"Failed to read document bytes from {path}: {exc}") from exc
    if b"\x00" in raw:
        raise InvalidRecordError(f"Document appears to be binary and cannot be loaded as text: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidRecordError(f"Document is not valid UTF-8 text: {path}") from exc
    if not text.strip():
        raise InvalidRecordError(f"Document is empty: {path}")

    normalized_path = str(path.resolve() if allow_symlinks else path.absolute())
    document_id = _stable_document_id(normalized_path, raw)
    return LoadedDocument(
        document_id=document_id,
        document_name=path.name,
        document_path=normalized_path,
        text=text,
        line_count=len(text.splitlines()),
        metadata={
            "extension": extension,
            "content_sha256": hashlib.sha256(raw).hexdigest(),
        },
    )


def _stable_document_id(document_path: str, raw_content: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(document_path.encode("utf-8"))
    digest.update(b"\0")
    digest.update(raw_content)
    return digest.hexdigest()[:16]
