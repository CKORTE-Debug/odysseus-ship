import sys
from datetime import datetime, timedelta, timezone

from verified_memory.models import MemoryClaim, SourceRef
from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows import build_prompt

NOW = datetime(2026, 6, 17, tzinfo=timezone.utc)


def test_prompt_workflow_builds_context_then_prompt_without_llm_calls(tmp_path, monkeypatch):
    db = tmp_path / "vm.sqlite3"
    store = SQLiteVerifiedMemoryStore(db)
    ref = SourceRef(
        source_type="local_document",
        source_id="doc-1",
        document_name="sop.md",
        document_path="/tmp/sop.md",
        chunk_id="doc-1:chunk:0001",
        line_start=1,
        line_end=1,
        quote="Users must connect to Wi-Fi.",
    )
    store.add_memory_claim(
        MemoryClaim(
            claim="Users must connect to Wi-Fi.",
            claim_type="requirement",
            status="verified",
            confidence="high",
            source_refs=[ref],
            last_verified_at=NOW - timedelta(days=1),
            stale_after_days=60,
        )
    )
    sys.modules.pop("src.llm_core", None)

    prompt = build_prompt("Wi-Fi", store, max_chunks=1, max_claims=5)

    assert prompt.messages[0]["role"] == "system"
    assert prompt.evidence_blocks["usable_verified_claims"]
    assert prompt.metadata["answer_generated"] is False
    assert "src.llm_core" not in sys.modules
