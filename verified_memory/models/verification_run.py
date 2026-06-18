"""Auditable verification-run model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from verified_memory.errors import InvalidRecordError
from verified_memory.models._helpers import datetime_to_json, metadata_dict, parse_datetime, require_non_empty, validate_allowed, utc_now

VERIFICATION_STATUSES = {"pending", "completed", "failed", "blocked"}
VERIFICATION_METHODS = {"local_only", "manual_web", "scheduled_refresh"}


@dataclass
class VerificationRun:
    claim_id: str
    status: str
    verification_method: str
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    sources_checked: list[dict[str, Any]] = field(default_factory=list)
    result_summary: str | None = None
    candidate_update_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        self.claim_id = require_non_empty(self.claim_id, "claim_id")
        self.status = validate_allowed(self.status, VERIFICATION_STATUSES, "status")
        self.verification_method = validate_allowed(
            self.verification_method,
            VERIFICATION_METHODS,
            "verification_method",
        )
        self.started_at = parse_datetime(self.started_at, "started_at") or utc_now()
        self.completed_at = parse_datetime(self.completed_at, "completed_at")
        if not isinstance(self.sources_checked, list):
            raise InvalidRecordError("sources_checked must be a list")
        self.sources_checked = [dict(item) for item in self.sources_checked]
        self.metadata = metadata_dict(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "started_at": datetime_to_json(self.started_at),
            "completed_at": datetime_to_json(self.completed_at),
            "status": self.status,
            "verification_method": self.verification_method,
            "sources_checked": list(self.sources_checked),
            "result_summary": self.result_summary,
            "candidate_update_id": self.candidate_update_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationRun":
        return cls(**data)
