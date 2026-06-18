"""Source document chunk model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from verified_memory.errors import InvalidRecordError
from verified_memory.models._helpers import datetime_to_json, metadata_dict, parse_datetime, require_non_empty, utc_now


@dataclass
class DocumentChunk:
    document_id: str
    document_name: str
    document_path: str
    chunk_id: str
    text: str
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        self.document_id = require_non_empty(self.document_id, "document_id")
        self.document_name = require_non_empty(self.document_name, "document_name")
        self.document_path = require_non_empty(self.document_path, "document_path")
        self.chunk_id = require_non_empty(self.chunk_id, "chunk_id")
        self.text = require_non_empty(self.text, "text")
        self.created_at = parse_datetime(self.created_at, "created_at") or utc_now()
        if self.page is not None and self.page < 1:
            raise InvalidRecordError("page must be >= 1 when provided")
        if self.line_start is not None and self.line_start < 1:
            raise InvalidRecordError("line_start must be >= 1 when provided")
        if self.line_end is not None and self.line_end < 1:
            raise InvalidRecordError("line_end must be >= 1 when provided")
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise InvalidRecordError("line_end must be greater than or equal to line_start")
        self.metadata = metadata_dict(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "document_path": self.document_path,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "page": self.page,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "created_at": datetime_to_json(self.created_at),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentChunk":
        return cls(**data)
