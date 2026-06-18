"""Conflict record model for verified-memory claims."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from verified_memory.models._helpers import datetime_to_json, metadata_dict, parse_datetime, require_non_empty, validate_allowed, utc_now

CONFLICT_TYPES = {"contradiction", "newer_source", "source_priority", "stale_vs_fresh", "manual_review"}
CONFLICT_STATUSES = {"open", "resolved", "ignored"}


@dataclass
class ConflictRecord:
    claim_id: str
    conflicting_claim_id: str
    conflict_type: str
    description: str
    created_at: datetime = field(default_factory=utc_now)
    status: str = "open"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        self.claim_id = require_non_empty(self.claim_id, "claim_id")
        self.conflicting_claim_id = require_non_empty(self.conflicting_claim_id, "conflicting_claim_id")
        self.conflict_type = validate_allowed(self.conflict_type, CONFLICT_TYPES, "conflict_type")
        self.description = require_non_empty(self.description, "description")
        self.created_at = parse_datetime(self.created_at, "created_at") or utc_now()
        self.status = validate_allowed(self.status, CONFLICT_STATUSES, "status")
        self.metadata = metadata_dict(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "conflicting_claim_id": self.conflicting_claim_id,
            "conflict_type": self.conflict_type,
            "description": self.description,
            "created_at": datetime_to_json(self.created_at),
            "status": self.status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConflictRecord":
        return cls(**data)
