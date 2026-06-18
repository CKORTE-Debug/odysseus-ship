import pytest

from verified_memory.errors import InvalidRecordError
from verified_memory.models import MemoryClaim, SourceRef


def test_valid_memory_claim_can_be_created():
    claim = MemoryClaim(
        claim="Microsoft Intune supports Autopilot deployment profiles.",
        claim_type="software_behavior",
        status="unverified",
        stale_after_days=None,
        metadata={"domain": "it_software", "unknown_future_key": True},
    )

    assert claim.claim_type == "software_behavior"
    assert claim.status == "unverified"
    assert claim.stale_after_days is None
    assert claim.metadata["unknown_future_key"] is True


def test_empty_claim_is_rejected():
    with pytest.raises(InvalidRecordError, match="claim must not be empty"):
        MemoryClaim(claim=" ", claim_type="software_behavior")


def test_invalid_status_is_rejected():
    with pytest.raises(InvalidRecordError, match="status must be one of"):
        MemoryClaim(claim="A claim", claim_type="software_behavior", status="fresh")


def test_invalid_confidence_is_rejected():
    with pytest.raises(InvalidRecordError, match="confidence must be one of"):
        MemoryClaim(claim="A claim", claim_type="software_behavior", confidence="certain")


def test_invalid_sensitivity_is_rejected():
    with pytest.raises(InvalidRecordError, match="sensitivity must be one of"):
        MemoryClaim(claim="A claim", claim_type="software_behavior", sensitivity="secret")


def test_verified_claim_with_no_source_refs_is_rejected():
    with pytest.raises(InvalidRecordError, match="verified MemoryClaim requires"):
        MemoryClaim(claim="A verified claim", claim_type="software_behavior", status="verified")


def test_verified_claim_with_source_ref_is_allowed():
    source = SourceRef(
        source_type="user_provided",
        source_id="user-note-1",
        quote="User explicitly provided this detail.",
    )
    claim = MemoryClaim(
        claim="User-provided detail is source-linked.",
        claim_type="user_fact",
        status="verified",
        confidence="high",
        source_refs=[source],
    )

    assert claim.status == "verified"
    assert claim.source_refs[0].source_id == "user-note-1"
