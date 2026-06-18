from datetime import datetime, timedelta, timezone

from verified_memory.models import MemoryClaim, SourceRef
from verified_memory.verification import evaluate_staleness

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)


def _verified_claim(**kwargs):
    source = SourceRef(source_type="user_provided", source_id="user-1")
    defaults = {
        "claim": "A sourced claim.",
        "claim_type": "software_behavior",
        "status": "verified",
        "confidence": "high",
        "source_refs": [source],
        "last_verified_at": NOW - timedelta(days=10),
        "stale_after_days": 60,
    }
    defaults.update(kwargs)
    return MemoryClaim(**defaults)


def test_fresh_claim():
    result = evaluate_staleness(_verified_claim(), now=NOW)

    assert result.status == "fresh"
    assert result.should_verify is False


def test_stale_claim():
    result = evaluate_staleness(
        _verified_claim(last_verified_at=NOW - timedelta(days=61), stale_after_days=60),
        now=NOW,
    )

    assert result.status == "stale"
    assert result.should_verify is True
    assert result.stale_since == NOW - timedelta(days=1)


def test_never_stale_claim():
    result = evaluate_staleness(_verified_claim(stale_after_days=None), now=NOW)

    assert result.status == "never_stale"
    assert result.should_verify is False


def test_unverified_claim():
    claim = MemoryClaim(claim="Unverified memory.", claim_type="software_behavior")

    result = evaluate_staleness(claim, now=NOW)

    assert result.status == "unverified"
    assert result.should_verify is True


def test_future_last_verified_at_is_invalid():
    result = evaluate_staleness(
        _verified_claim(last_verified_at=NOW + timedelta(minutes=1)),
        now=NOW,
    )

    assert result.status == "invalid"
    assert result.should_verify is True


def test_archived_claim():
    claim = MemoryClaim(claim="Archived memory.", claim_type="software_behavior", status="archived")

    result = evaluate_staleness(claim, now=NOW)

    assert result.status == "archived"
    assert result.should_verify is False


def test_contradicted_claim():
    claim = MemoryClaim(claim="Contradicted memory.", claim_type="software_behavior", status="contradicted")

    result = evaluate_staleness(claim, now=NOW)

    assert result.status == "contradicted"
    assert result.should_verify is False


def test_timezone_aware_utc_behavior():
    eastern_like = datetime(2026, 6, 17, 7, 0, tzinfo=timezone(timedelta(hours=-5)))
    result = evaluate_staleness(
        _verified_claim(last_verified_at="2026-06-17T00:00:00Z", stale_after_days=1),
        now=eastern_like,
    )

    assert result.status == "fresh"
    assert result.checked_at.tzinfo == timezone.utc
