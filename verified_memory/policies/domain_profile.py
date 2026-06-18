"""Domain profile loading for deterministic verified-memory policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from verified_memory.errors import InvalidRecordError
from verified_memory.policies.default_domain_profiles import DEFAULT_DOMAIN_PROFILES


@dataclass(frozen=True)
class DomainProfile:
    name: str
    description: str
    default_stale_after_days_by_claim_type: dict[str, int | None]
    source_priority: list[str]
    web_search_allowed: bool
    manual_approval_required: bool
    never_final_sources: list[str]
    requires_disclaimer: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def stale_after_days_for(self, claim_type: str) -> int | None:
        """Return the staleness window for a claim type, or None for never stale."""

        return self.default_stale_after_days_by_claim_type.get(claim_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "default_stale_after_days_by_claim_type": dict(self.default_stale_after_days_by_claim_type),
            "source_priority": list(self.source_priority),
            "web_search_allowed": self.web_search_allowed,
            "manual_approval_required": self.manual_approval_required,
            "never_final_sources": list(self.never_final_sources),
            "requires_disclaimer": self.requires_disclaimer,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DomainProfile":
        required = {
            "name",
            "description",
            "default_stale_after_days_by_claim_type",
            "source_priority",
            "web_search_allowed",
            "manual_approval_required",
            "never_final_sources",
            "requires_disclaimer",
        }
        missing = sorted(required - set(data.keys()))
        if missing:
            raise InvalidRecordError(f"DomainProfile missing required fields: {missing}")
        return cls(
            name=str(data["name"]),
            description=str(data["description"]),
            default_stale_after_days_by_claim_type=dict(data["default_stale_after_days_by_claim_type"]),
            source_priority=list(data["source_priority"]),
            web_search_allowed=bool(data["web_search_allowed"]),
            manual_approval_required=bool(data["manual_approval_required"]),
            never_final_sources=list(data["never_final_sources"]),
            requires_disclaimer=bool(data["requires_disclaimer"]),
            metadata=dict(data.get("metadata") or {}),
        )


def load_domain_profile(name: str, *, fallback_to_general: bool = True) -> DomainProfile:
    """Load a built-in domain profile by name."""

    profile_name = str(name or "").strip().lower()
    data = DEFAULT_DOMAIN_PROFILES.get(profile_name)
    if data is None and fallback_to_general:
        data = DEFAULT_DOMAIN_PROFILES["general"]
    if data is None:
        raise InvalidRecordError(f"Unknown domain profile: {name!r}")
    return DomainProfile.from_dict(data)


def list_domain_profiles() -> list[str]:
    """Return available built-in domain profile names."""

    return sorted(DEFAULT_DOMAIN_PROFILES)
