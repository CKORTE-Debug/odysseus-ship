import importlib
import json
import sys

import pytest

from verified_memory.config import VerifiedMemoryGenerationConfig
from verified_memory.contracts import (
    VerifiedMemoryAnswerRequest,
    VerifiedMemoryServiceEnvelope,
    assert_safe_service_response,
)
from verified_memory.service import VerifiedMemoryService
from verified_memory.storage import SQLiteVerifiedMemoryStore


def test_service_envelope_success_serializes_to_json():
    envelope = VerifiedMemoryServiceEnvelope.success(
        "build_context",
        {"answer": "ok", "items": [1, 2]},
        audit={"operation": "build_context"},
        metadata={"source": "test"},
    )

    assert envelope.to_dict()["ok"] is True
    json.dumps(envelope.to_dict())


def test_service_envelope_failure_serializes_to_json():
    envelope = VerifiedMemoryServiceEnvelope.failure(
        "generate_answer",
        "validation failed",
        audit={"operation": "generate_answer", "answer_validated": False},
    )

    assert envelope.to_dict()["ok"] is False
    json.dumps(envelope.to_dict())


def test_service_contract_does_not_import_llm_core():
    sys.modules.pop("src.llm_core", None)
    importlib.import_module("verified_memory.contracts.service_contract")
    assert "src.llm_core" not in sys.modules


def test_service_contract_does_not_import_forbidden_integration_modules():
    forbidden = {"chromadb", "routes.search_routes", "routes.research_routes", "src.memory"}
    for module_name in forbidden:
        sys.modules.pop(module_name, None)

    importlib.import_module("verified_memory.contracts.service_contract")

    assert forbidden.isdisjoint(sys.modules)


def test_assert_safe_service_response_accepts_valid_generated_answer_response():
    assert_safe_service_response(
        {
            "operation": "generate_answer",
            "answer": "Use Wi-Fi.",
            "safe_to_show": True,
            "validation_severity": "pass",
            "audit": {"answer_validated": True},
        }
    )


def test_assert_safe_service_response_rejects_missing_validation_metadata():
    with pytest.raises(ValueError, match="validation"):
        assert_safe_service_response(
            {
                "operation": "generate_answer",
                "answer": "Use Wi-Fi.",
                "safe_to_show": True,
                "audit": {"answer_validated": True},
            }
        )


def test_assert_safe_service_response_rejects_missing_audit_metadata():
    with pytest.raises(ValueError, match="audit"):
        assert_safe_service_response(
            {
                "operation": "generate_answer",
                "answer": "Use Wi-Fi.",
                "safe_to_show": True,
                "validation_severity": "pass",
            }
        )


def test_assert_safe_service_response_rejects_answer_validated_false():
    with pytest.raises(ValueError, match="answer_validated=true"):
        assert_safe_service_response(
            {
                "operation": "generate_answer",
                "answer": "Use Wi-Fi.",
                "safe_to_show": True,
                "validation_severity": "pass",
                "audit": {"answer_validated": False},
            }
        )


@pytest.mark.asyncio
async def test_verified_memory_service_generated_response_can_be_converted_into_envelope(tmp_path):
    service = VerifiedMemoryService(SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3"))
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    chunk_id = service.ingest_document(doc)["chunk_ids"][0]

    async def fake_llm(messages, **kwargs):
        return f"Users must connect to Wi-Fi during OOBE. [{chunk_id}]"

    response = await service.generate_answer(
        VerifiedMemoryAnswerRequest(
            question="Wi-Fi?",
            generation_config=VerifiedMemoryGenerationConfig(model="fake"),
        ),
        llm_call=fake_llm,
    )
    payload = response.to_dict()

    assert_safe_service_response(payload)
    envelope = service.envelope(payload, operation="generate_answer")

    assert envelope.ok is True
    assert envelope.to_dict()["payload"]["audit"]["answer_validated"] is True
    json.dumps(envelope.to_dict())


def test_envelope_does_not_mutate_payload():
    payload = {"nested": {"value": 1}, "items": ["a"]}
    before = {"nested": {"value": 1}, "items": ["a"]}

    envelope = VerifiedMemoryServiceEnvelope.success("build_context", payload)
    envelope_dict = envelope.to_dict()
    envelope_dict["payload"]["nested"]["value"] = 2
    envelope_dict["payload"]["items"].append("changed")

    assert payload == before
    assert payload["items"] == ["a"]


@pytest.mark.asyncio
async def test_full_service_response_remains_json_serializable(tmp_path):
    service = VerifiedMemoryService(SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3"))
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    chunk_id = service.ingest_document(doc)["chunk_ids"][0]

    async def fake_llm(messages, **kwargs):
        return f"Users must connect to Wi-Fi during OOBE. [{chunk_id}]"

    response = await service.generate_answer(
        VerifiedMemoryAnswerRequest(question="Wi-Fi?", generation_config=VerifiedMemoryGenerationConfig(model="fake")),
        llm_call=fake_llm,
    )

    json.dumps(response.to_dict())
