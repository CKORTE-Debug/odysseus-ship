"""Deterministic staleness evaluation for verified-memory claims."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from verified_memory.models import MemoryClaim
from verified_memory.models._helpers import datetime_to_json, parse_datetime, utc_now

STALENESS_STATUSES = {
    "fresh",
    "stale",
    "never_stale",
    "unverified",
    "invalid",
    "archived",
    "contradicted",
}


@dataclass(frozen=True)
class StalenessResult:
    """Structured result returned by the staleness evaluator."""

    status: str
    reason: str
    checked_at: datetime = field(default_factory=utc_now)
    stale_since: datetime | None = None
    should_verify: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "checked_at": datetime_to_json(self.checked_at),
            "stale_since": datetime_to_json(self.stale_since),
            "should_verify": self.should_verify,
        }


def evaluate_staleness(claim: MemoryClaim, *, now: datetime | None = None) -> StalenessResult:
    """Evaluate a claim's freshness using deterministic timestamp rules."""

    checked_at = parse_datetime(now, "now") or utc_now()

    if claim.status == "archived":
        return StalenessResult(
            status="archived",
            reason="Claim is archived and should not be used as active evidence.",
            checked_at=checked_at,
            should_verify=False,
        )

    if claim.status == "contradicted":
        return StalenessResult(
            status="contradicted",
            reason="Claim is contradicted and should only be used for conflict context.",
            checked_at=checked_at,
            should_verify=False,
        )

    if claim.last_verified_at is None:
        return StalenessResult(
            status="unverified",
            reason="Claim has no last_verified_at timestamp.",
            checked_at=checked_at,
            should_verify=True,
        )

    last_verified_at = parse_datetime(claim.last_verified_at, "last_verified_at")
    if last_verified_at is None:
        return StalenessResult(
            status="unverified",
            reason="Claim has no last_verified_at timestamp.",
            checked_at=checked_at,
            should_verify=True,
        )

    if last_verified_at > checked_at:
        return StalenessResult(
            status="invalid",
            reason="Claim last_verified_at is in the future.",
            checked_at=checked_at,
            should_verify=True,
        )

    if claim.stale_after_days is None:
        return StalenessResult(
            status="never_stale",
            reason="Claim has no stale_after_days expiry.",
            checked_at=checked_at,
            should_verify=False,
        )

    stale_since = last_verified_at + timedelta(days=claim.stale_after_days)
    if stale_since < checked_at:
        return StalenessResult(
            status="stale",
            reason=f"Claim exceeded stale_after_days={claim.stale_after_days}.",
            checked_at=checked_at,
            stale_since=stale_since.astimezone(timezone.utc),
            should_verify=True,
        )

    return StalenessResult(
        status="fresh",
        reason=f"Claim verified within stale_after_days={claim.stale_after_days}.",
        checked_at=checked_at,
        stale_since=stale_since.astimezone(timezone.utc),
        should_verify=False,
    )
