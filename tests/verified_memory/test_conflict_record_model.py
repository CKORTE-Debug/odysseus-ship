import pytest

from verified_memory.errors import InvalidRecordError
from verified_memory.models import ConflictRecord


def test_conflict_record_can_be_created():
    conflict = ConflictRecord(
        claim_id="claim-1",
        conflicting_claim_id="claim-2",
        conflict_type="contradiction",
        description="Claims disagree about the current setup path.",
        metadata={"reviewer": "local_user"},
    )

    assert conflict.status == "open"
    assert conflict.conflict_type == "contradiction"
    assert conflict.metadata["reviewer"] == "local_user"


def test_conflict_record_rejects_invalid_status():
    with pytest.raises(InvalidRecordError, match="status must be one of"):
        ConflictRecord(
            claim_id="claim-1",
            conflicting_claim_id="claim-2",
            conflict_type="contradiction",
            description="Invalid status example.",
            status="pending",
        )
