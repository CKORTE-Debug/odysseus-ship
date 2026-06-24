import importlib
import json
import sys

import pytest

from verified_memory.config import VerifiedMemoryGenerationConfig
from verified_memory.contracts import VerifiedMemoryAnswerRequest, VerifiedMemoryAnswerResponse
from verified_memory.service import VerifiedMemoryService, VerifiedMemoryServiceError
from verified_memory.storage import SQLiteVerifiedMemoryStore


def _service_with_doc(tmp_path):
    service = VerifiedMemoryService(SQLiteVerifiedMemoryStore(tmp_path / "vm.sqlite3"))
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    ingest = service.ingest_document(doc)
    return service, ingest["chunk_ids"][0]


def test_service_constructs_from_store_and_db_path(tmp_path):
    store = SQLiteVerifiedMemoryStore(tmp_path / "store.sqlite3")
    assert VerifiedMemoryService(store).store is store
    assert isinstance(VerifiedMemoryService.from_db_path(tmp_path / "path.sqlite3").store, SQLiteVerifiedMemoryStore)


def test_service_ingests_txt_and_markdown_documents(tmp_path):
    service = VerifiedMemoryService.from_db_path(tmp_path / "vm.sqlite3")
    txt = tmp_path / "guide.txt"
    md = tmp_path / "guide.md"
    txt.write_text("Users must connect to Wi-Fi.\n", encoding="utf-8")
    md.write_text("# Guide\nAdmins should check Teams.\n", encoding="utf-8")

    txt_result = service.ingest_document(txt)
    md_result = service.ingest_document(md)

    assert txt_result["chunks_created"] == 1
    assert md_result["chunks_created"] == 1
    assert txt_result["audit"]["operation"] == "ingest_document"
    json.dumps(txt_result)


def test_service_extract_claims_uses_workflow_and_stores_candidates(tmp_path):
    service, _ = _service_with_doc(tmp_path)

    result = service.extract_claims(default_sensitivity="public", allowed_web_search=False)

    assert result["operation"] == "extract_claims"
    assert result["claims_created"] == 1
    claim = service.store.get_memory_claim(result["claim_ids"][0])
    assert claim.status == "unverified"
    assert claim.sensitivity == "public"
    assert result["audit"]["web_called"] is False


def test_service_build_context_and_prompt_are_serializable(tmp_path):
    service, chunk_id = _service_with_doc(tmp_path)

    context = service.build_context("What does OOBE require?")
    prompt = service.build_prompt("What does OOBE require?")

    assert context["operation"] == "build_context"
    assert context["retrieved_chunks"][0]["chunk_id"] == chunk_id
    assert "warnings" in context
    assert prompt["operation"] == "build_prompt"
    assert prompt["messages"]
    assert chunk_id in prompt["evidence_blocks"]["citation_source_refs"]
    json.dumps(context)
    json.dumps(prompt)


def test_service_validate_answer_detects_invented_citations(tmp_path):
    service, _ = _service_with_doc(tmp_path)

    result = service.validate_answer("Wi-Fi?", "Use Wi-Fi. [invented]")

    assert result["validation_severity"] == "error"
    assert result["safe_to_show"] is False
    assert result["audit"]["answer_validated"] is True
    assert "invented_citation" in result["audit"]["validation_issue_codes"]


@pytest.mark.asyncio
async def test_service_generate_answer_uses_fake_llm_and_returns_contract(tmp_path):
    service, chunk_id = _service_with_doc(tmp_path)
    calls = []

    async def fake_llm(messages, **kwargs):
        calls.append((messages, kwargs))
        return f"Users must connect to Wi-Fi during OOBE. [{chunk_id}]"

    request = VerifiedMemoryAnswerRequest(
        question="Wi-Fi?",
        generation_config=VerifiedMemoryGenerationConfig(model="fake", temperature=0.2),
    )
    response = await service.generate_answer(request, llm_call=fake_llm)

    assert calls
    assert isinstance(response, VerifiedMemoryAnswerResponse)
    assert response.safe_to_show is True
    assert response.validation_severity == "pass"
    assert response.audit["operation"] == "generate_answer"
    assert response.audit["llm_called"] is True
    assert response.audit["config_validated"] is True
    assert response.audit["answer_validated"] is True
    json.dumps(response.to_dict())


@pytest.mark.asyncio
async def test_service_generate_answer_safe_to_show_false_for_invented_citation(tmp_path):
    service, _ = _service_with_doc(tmp_path)

    async def fake_llm(messages, **kwargs):
        return "Users must connect to Wi-Fi during OOBE. [invented]"

    request = VerifiedMemoryAnswerRequest(question="Wi-Fi?", generation_config=VerifiedMemoryGenerationConfig(model="fake"))
    response = await service.generate_answer(request, llm_call=fake_llm)

    assert response.safe_to_show is False
    assert response.validation_severity == "error"
    assert "invented_citation" in response.audit["validation_issue_codes"]


@pytest.mark.asyncio
async def test_service_generate_answer_does_not_mutate_chunks_or_claims(tmp_path):
    service, chunk_id = _service_with_doc(tmp_path)
    claims_result = service.extract_claims()
    chunks_before = [chunk.to_dict() for chunk in service.store.list_document_chunks()]
    claims_before = [claim.to_dict() for claim in service.store.list_memory_claims()]

    async def fake_llm(messages, **kwargs):
        return f"Users must connect to Wi-Fi during OOBE. [{chunk_id}]"

    request = VerifiedMemoryAnswerRequest(question="Wi-Fi?", generation_config=VerifiedMemoryGenerationConfig(model="fake"))
    await service.generate_answer(request, llm_call=fake_llm)

    assert claims_result["claims_created"] == 1
    assert [chunk.to_dict() for chunk in service.store.list_document_chunks()] == chunks_before
    assert [claim.to_dict() for claim in service.store.list_memory_claims()] == claims_before


@pytest.mark.asyncio
async def test_service_generate_answer_with_fake_does_not_import_llm_core(tmp_path):
    service, chunk_id = _service_with_doc(tmp_path)
    sys.modules.pop("src.llm_core", None)

    async def fake_llm(messages, **kwargs):
        return f"Users must connect to Wi-Fi during OOBE. [{chunk_id}]"

    request = VerifiedMemoryAnswerRequest(question="Wi-Fi?", generation_config=VerifiedMemoryGenerationConfig(model="fake"))
    await service.generate_answer(request, llm_call=fake_llm)

    assert "src.llm_core" not in sys.modules


@pytest.mark.asyncio
async def test_service_rejects_invalid_real_llm_config_before_llm_core_import(tmp_path):
    service, _ = _service_with_doc(tmp_path)
    sys.modules.pop("src.llm_core", None)
    request = VerifiedMemoryAnswerRequest(
        question="Wi-Fi?",
        generation_config=VerifiedMemoryGenerationConfig(model="", allow_network_llm=True, endpoint_url="http://example.invalid"),
    )

    with pytest.raises(VerifiedMemoryServiceError) as excinfo:
        await service.generate_answer(request)

    assert excinfo.value.audit["llm_called"] is False
    assert "src.llm_core" not in sys.modules


def test_contract_objects_remain_side_effect_free():
    before = set(sys.modules)
    request = VerifiedMemoryAnswerRequest(question="Wi-Fi?", generation_config=VerifiedMemoryGenerationConfig(model="fake"))
    response = VerifiedMemoryAnswerResponse(question="Wi-Fi?", answer="", safe_to_show=False, validation={})

    assert request.to_dict()["question"] == "Wi-Fi?"
    assert response.to_dict()["operation"] == "generate_answer"
    assert set(sys.modules) == before


def test_service_does_not_import_forbidden_integration_modules():
    forbidden = {"chromadb", "routes.search_routes", "routes.research_routes", "src.memory"}
    for name in forbidden:
        sys.modules.pop(name, None)

    importlib.import_module("verified_memory.service.verified_memory_service")

    assert forbidden.isdisjoint(sys.modules)
