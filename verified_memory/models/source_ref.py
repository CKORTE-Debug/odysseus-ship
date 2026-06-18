"""Source reference model for verified memory evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from verified_memory.errors import InvalidRecordError
from verified_memory.models._helpers import datetime_to_json, parse_datetime, validate_allowed, utc_now

SOURCE_TYPES = {
    "local_document",
    "web_source",
    "user_provided",
    "system_generated",
    "legacy_memory",
}


@dataclass
class SourceRef:
    source_type: str
    source_id: str | None = None
    document_name: str | None = None
    document_path: str | None = None
    chunk_id: str | None = None
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    quote: str | None = None
    url: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.source_type = validate_allowed(self.source_type, SOURCE_TYPES, "source_type")
        self.created_at = parse_datetime(self.created_at, "created_at") or utc_now()
        if self.source_id is not None:
            self.source_id = str(self.source_id).strip() or None
        if self.url is not None:
            self.url = str(self.url).strip() or None
        if self.source_type == "web_source" and not self.url:
            raise InvalidRecordError("web_source SourceRef requires url")
        if self.line_start is not None and self.line_start < 1:
            raise InvalidRecordError("line_start must be >= 1 when provided")
        if self.line_end is not None and self.line_end < 1:
            raise InvalidRecordError("line_end must be >= 1 when provided")
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise InvalidRecordError("line_end must be greater than or equal to line_start")
        if self.page is not None and self.page < 1:
            raise InvalidRecordError("page must be >= 1 when provided")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "document_name": self.document_name,
            "document_path": self.document_path,
            "chunk_id": self.chunk_id,
            "page": self.page,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "quote": self.quote,
            "url": self.url,
            "created_at": datetime_to_json(self.created_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceRef":
        return cls(**data)
