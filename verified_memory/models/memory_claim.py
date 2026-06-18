"""Structured memory claim model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from verified_memory.errors import InvalidRecordError
from verified_memory.models._helpers import (
    datetime_to_json,
    metadata_dict,
    parse_datetime,
    require_non_empty,
    validate_allowed,
    utc_now,
)
from verified_memory.models.source_ref import SourceRef

CLAIM_STATUSES = {"unverified", "verified", "stale", "contradicted", "archived"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
SENSITIVITY_LEVELS = {"public", "private", "client_confidential", "personal_sensitive"}


@dataclass
class MemoryClaim:
    claim: str
    claim_type: str
    source_refs: list[SourceRef] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    last_verified_at: datetime | None = None
    stale_after_days: int | None = None
    status: str = "unverified"
    confidence: str = "low"
    sensitivity: str = "private"
    verification_policy: str = "local_only"
    allowed_web_search: bool = False
    superseded_by: str | None = None
    conflicts_with: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        self.claim = require_non_empty(self.claim, "claim")
        self.claim_type = require_non_empty(self.claim_type, "claim_type")
        self.status = validate_allowed(self.status, CLAIM_STATUSES, "status")
        self.confidence = validate_allowed(self.confidence, CONFIDENCE_LEVELS, "confidence")
        self.sensitivity = validate_allowed(self.sensitivity, SENSITIVITY_LEVELS, "sensitivity")
        self.created_at = parse_datetime(self.created_at, "created_at") or utc_now()
        self.last_verified_at = parse_datetime(self.last_verified_at, "last_verified_at")
        if self.stale_after_days is not None and self.stale_after_days < 0:
            raise InvalidRecordError("stale_after_days must be >= 0 or None")
        self.source_refs = [ref if isinstance(ref, SourceRef) else SourceRef.from_dict(ref) for ref in self.source_refs]
        if self.status == "verified" and not self.source_refs:
            raise InvalidRecordError("verified MemoryClaim requires at least one source_ref")
        if not isinstance(self.allowed_web_search, bool):
            raise InvalidRecordError("allowed_web_search must be a bool")
        self.conflicts_with = [str(item) for item in (self.conflicts_with or [])]
        self.metadata = metadata_dict(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim": self.claim,
            "claim_type": self.claim_type,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "created_at": datetime_to_json(self.created_at),
            "last_verified_at": datetime_to_json(self.last_verified_at),
            "stale_after_days": self.stale_after_days,
            "status": self.status,
            "confidence": self.confidence,
            "sensitivity": self.sensitivity,
            "verification_policy": self.verification_policy,
            "allowed_web_search": self.allowed_web_search,
            "superseded_by": self.superseded_by,
            "conflicts_with": list(self.conflicts_with),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryClaim":
        return cls(**data)
