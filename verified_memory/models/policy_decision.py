"""Policy decision model for future privacy/source/staleness decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from verified_memory.models._helpers import datetime_to_json, metadata_dict, parse_datetime, require_non_empty, utc_now


@dataclass
class PolicyDecision:
    decision_type: str
    input_text: str
    result: str
    reason: str
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        self.decision_type = require_non_empty(self.decision_type, "decision_type")
        self.input_text = require_non_empty(self.input_text, "input_text")
        self.result = require_non_empty(self.result, "result")
        self.reason = require_non_empty(self.reason, "reason")
        self.created_at = parse_datetime(self.created_at, "created_at") or utc_now()
        self.metadata = metadata_dict(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "decision_type": self.decision_type,
            "input_text": self.input_text,
            "result": self.result,
            "reason": self.reason,
            "created_at": datetime_to_json(self.created_at),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyDecision":
        return cls(**data)
