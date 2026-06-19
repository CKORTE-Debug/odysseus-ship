import socket

import pytest

from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows import generate_answer, ingest_document


def _store_with_doc(tmp_path):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    store = SQLiteVerifiedMemoryStore(db)
    ingest_document(document, store)
    return store


@pytest.mark.asyncio
async def test_workflow_builds_prompt_generates_answer_and_validates(tmp_path):
    store = _store_with_doc(tmp_path)
    ref = store.list_document_chunks()[0].chunk_id
    calls = []

    async def fake_llm(messages, **kwargs):
        calls.append(messages)
        return f"Users must connect to Wi-Fi during OOBE. [{ref}]"

    result = await generate_answer("What does the SOP say about Wi-Fi?", store, llm_call=fake_llm)

    assert calls
    assert "Original question:" in calls[0][1]["content"]
    assert result.safe_to_show is True
    assert result.validation_result.severity == "pass"
    assert result.prompt_metadata["answer_generated"] is True


@pytest.mark.asyncio
async def test_workflow_does_not_mutate_stored_chunks_or_claims(tmp_path):
    store = _store_with_doc(tmp_path)
    chunks_before = [chunk.to_dict() for chunk in store.list_document_chunks()]
    claims_before = [claim.to_dict() for claim in store.list_memory_claims()]
    ref = chunks_before[0]["chunk_id"]

    async def fake_llm(messages, **kwargs):
        return f"Users must connect to Wi-Fi during OOBE. [{ref}]"

    await generate_answer("Wi-Fi?", store, llm_call=fake_llm)

    assert [chunk.to_dict() for chunk in store.list_document_chunks()] == chunks_before
    assert [claim.to_dict() for claim in store.list_memory_claims()] == claims_before


@pytest.mark.asyncio
async def test_workflow_does_not_call_web_or_network(tmp_path, monkeypatch):
    store = _store_with_doc(tmp_path)

    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    async def fake_llm(messages, **kwargs):
        return "Users must connect to Wi-Fi during OOBE."

    result = await generate_answer("Wi-Fi?", store, llm_call=fake_llm)

    assert result.metadata["web_called"] is False
    assert result.metadata["llm_called"] is True
