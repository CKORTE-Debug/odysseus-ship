import ast
import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.verified_memory_routes import setup_verified_memory_routes
from verified_memory.service import VerifiedMemoryService


ROUTE_PATH = Path("routes/verified_memory_routes.py")


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(setup_verified_memory_routes())
    return TestClient(app)


class FakeService:
    calls = []

    def __init__(self, db_path):
        self.db_path = db_path

    @classmethod
    def from_db_path(cls, db_path):
        return cls(db_path)

    def build_context(self, question, *, max_chunks=5, max_claims=5, include_archived=False):
        self.calls.append(("build_context", self.db_path, question, max_chunks, max_claims, include_archived))
        return {"operation": "build_context", "question": question, "retrieved_chunks": [], "matched_claims": [], "audit": {"llm_called": False, "web_called": False}}

    def build_prompt(self, question, *, max_chunks=5, max_claims=5, include_archived=False):
        self.calls.append(("build_prompt", self.db_path, question, max_chunks, max_claims, include_archived))
        return {"operation": "build_prompt", "messages": [], "evidence_blocks": {"citation_source_refs": []}, "audit": {"llm_called": False, "web_called": False}}

    def validate_answer(self, question, answer, *, max_chunks=5, max_claims=5, include_archived=False):
        self.calls.append(("validate_answer", self.db_path, question, answer, max_chunks, max_claims, include_archived))
        invented = "invented" in answer
        return {
            "operation": "validate_answer",
            "validation": {"severity": "error" if invented else "pass", "issues": ([{"code": "invented_citation"}] if invented else [])},
            "validation_severity": "error" if invented else "pass",
            "safe_to_show": not invented,
            "audit": {"llm_called": False, "web_called": False, "answer_validated": True, "validation_issue_codes": (["invented_citation"] if invented else [])},
        }


@pytest.fixture()
def fake_service(monkeypatch):
    FakeService.calls = []
    monkeypatch.setattr("routes.verified_memory_routes.VerifiedMemoryService", FakeService)
    return FakeService


def test_health_route_returns_ok_capabilities(client):
    response = client.get("/api/verified-memory/health")
    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "verified_memory_health"
    assert body["ok"] is True
    assert body["capabilities"]["build_context"] is True
    assert body["capabilities"]["build_prompt"] is True
    assert body["capabilities"]["validate_answer"] is True


def test_routes_do_not_expose_generate_ingest_or_extract_capabilities(client):
    capabilities = client.get("/api/verified-memory/health").json()["capabilities"]
    assert capabilities["generate_answer"] is False
    assert capabilities["ingest_document"] is False
    assert capabilities["extract_claims"] is False


def test_context_route_calls_verified_memory_service_build_context(client, fake_service):
    response = client.post("/api/verified-memory/context", json={"question": "Wi-Fi?", "db_path": "vm.db", "max_chunks": 3, "max_claims": 2, "include_archived": True})
    assert response.status_code == 200
    assert fake_service.calls == [("build_context", "vm.db", "Wi-Fi?", 3, 2, True)]
    assert response.json()["operation"] == "build_context"


def test_prompt_route_calls_verified_memory_service_build_prompt(client, fake_service):
    response = client.post("/api/verified-memory/prompt", json={"question": "Wi-Fi?", "db_path": "vm.db"})
    assert response.status_code == 200
    assert fake_service.calls[0][0] == "build_prompt"
    assert response.json()["payload"]["evidence_blocks"]["citation_source_refs"] == []


def test_validate_answer_route_calls_service_and_detects_invented_citations(client, fake_service):
    response = client.post("/api/verified-memory/validate-answer", json={"question": "Wi-Fi?", "answer": "Use Wi-Fi. [invented]", "db_path": "vm.db"})
    assert response.status_code == 200
    body = response.json()
    assert fake_service.calls[0][0] == "validate_answer"
    assert body["payload"]["safe_to_show"] is False
    assert "invented_citation" in body["payload"]["audit"]["validation_issue_codes"]


def test_routes_return_json_serializable_responses(client, fake_service):
    responses = [
        client.get("/api/verified-memory/health").json(),
        client.post("/api/verified-memory/context", json={"question": "Wi-Fi?", "db_path": "vm.db"}).json(),
        client.post("/api/verified-memory/prompt", json={"question": "Wi-Fi?", "db_path": "vm.db"}).json(),
        client.post("/api/verified-memory/validate-answer", json={"question": "Wi-Fi?", "answer": "Use Wi-Fi.", "db_path": "vm.db"}).json(),
    ]
    for body in responses:
        json.dumps(body)


@pytest.mark.parametrize("field", ["model", "endpoint_url", "allow_network_llm", "generation_config"])
def test_routes_do_not_accept_generation_fields(client, field):
    response = client.post("/api/verified-memory/context", json={"question": "Wi-Fi?", "db_path": "vm.db", field: "blocked"})
    assert response.status_code == 422


def test_missing_db_path_returns_structured_error(client):
    response = client.post("/api/verified-memory/context", json={"question": "Wi-Fi?"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["ok"] is False
    assert detail["error"]["code"] == "missing_db_path"


def test_invalid_request_returns_fastapi_validation_error(client):
    response = client.post("/api/verified-memory/context", json={"db_path": "vm.db"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_real_routes_validate_answer_with_store_detects_invented_citation(client, tmp_path):
    service = VerifiedMemoryService.from_db_path(tmp_path / "vm.sqlite3")
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    service.ingest_document(doc)

    response = client.post("/api/verified-memory/validate-answer", json={"question": "Wi-Fi?", "answer": "Use Wi-Fi. [invented]", "db_path": str(tmp_path / "vm.sqlite3")})

    assert response.status_code == 200
    assert response.json()["payload"]["validation_severity"] == "error"


def test_routes_do_not_import_forbidden_modules():
    forbidden = {"src.llm_core", "src.memory", "chromadb", "routes.search_routes", "routes.research_routes"}
    for name in forbidden:
        sys.modules.pop(name, None)
    importlib.reload(importlib.import_module("routes.verified_memory_routes"))
    assert forbidden.isdisjoint(sys.modules)


def test_route_source_does_not_call_forbidden_integrations():
    tree = ast.parse(ROUTE_PATH.read_text(encoding="utf-8"))
    imported = set()
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    forbidden_imports = {"src.llm_core", "src.memory", "chromadb", "routes.search_routes", "routes.research_routes"}
    forbidden_calls = {"generate_answer", "web_search", "research", "ChromaDB"}
    assert forbidden_imports.isdisjoint(imported)
    assert forbidden_calls.isdisjoint(called)


def test_health_route_shows_admin_routes_disabled_by_default(client):
    capabilities = client.get("/api/verified-memory/health").json()["capabilities"]
    assert capabilities["admin_routes_enabled"] is False
    assert capabilities["ingest_document"] is False
    assert capabilities["extract_claims"] is False


def test_health_route_shows_admin_routes_enabled_when_opted_in(client, monkeypatch):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    capabilities = client.get("/api/verified-memory/health").json()["capabilities"]
    assert capabilities["admin_routes_enabled"] is True
    assert capabilities["ingest_document"] is True
    assert capabilities["extract_claims"] is True
    assert capabilities["generate_answer"] is False


def test_admin_ingest_route_returns_structured_disabled_error_by_default(client, tmp_path):
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    response = client.post("/api/verified-memory/admin/ingest", json={"db_path": str(tmp_path / "vm.sqlite3"), "path": str(doc), "confirm_mutation": True})
    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "admin_ingest_document"
    assert body["ok"] is False
    assert body["error"]["code"] == "admin_routes_disabled"
    assert body["audit"]["mutation_attempted"] is False
    assert body["audit"]["mutation_performed"] is False


def test_admin_extract_route_returns_structured_disabled_error_by_default(client, tmp_path):
    response = client.post("/api/verified-memory/admin/extract-claims", json={"db_path": str(tmp_path / "vm.sqlite3"), "confirm_mutation": True})
    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "admin_extract_claims"
    assert body["ok"] is False
    assert body["error"]["code"] == "admin_routes_disabled"
    assert body["audit"]["mutation_attempted"] is False
    assert body["audit"]["mutation_performed"] is False


def test_disabled_admin_ingest_does_not_call_service(client, fake_service, tmp_path):
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    response = client.post("/api/verified-memory/admin/ingest", json={"db_path": "vm.db", "path": str(doc), "confirm_mutation": True})
    assert response.status_code == 200
    assert fake_service.calls == []


def test_disabled_admin_extract_does_not_call_service(client, fake_service):
    response = client.post("/api/verified-memory/admin/extract-claims", json={"db_path": "vm.db", "confirm_mutation": True})
    assert response.status_code == 200
    assert fake_service.calls == []


def test_enabled_admin_ingest_requires_confirm_mutation(client, monkeypatch, tmp_path):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    response = client.post("/api/verified-memory/admin/ingest", json={"db_path": str(tmp_path / "vm.sqlite3"), "path": str(doc)})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "mutation_not_confirmed"


def test_enabled_admin_extract_requires_confirm_mutation(client, monkeypatch, tmp_path):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    response = client.post("/api/verified-memory/admin/extract-claims", json={"db_path": str(tmp_path / "vm.sqlite3")})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "mutation_not_confirmed"


def test_enabled_admin_ingest_rejects_missing_db_path(client, monkeypatch, tmp_path):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    response = client.post("/api/verified-memory/admin/ingest", json={"path": str(doc), "confirm_mutation": True})
    assert response.status_code == 422


@pytest.mark.parametrize("bad_path", ["https://example.com/sop.txt", "http://example.com/sop.md"])
def test_enabled_admin_ingest_rejects_url_paths(client, monkeypatch, bad_path, tmp_path):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    response = client.post("/api/verified-memory/admin/ingest", json={"db_path": str(tmp_path / "vm.sqlite3"), "path": bad_path, "confirm_mutation": True})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_path"


@pytest.mark.parametrize("name", ["sop.pdf", "sop.docx", "sop.html"])
def test_enabled_admin_ingest_rejects_unsupported_extensions(client, monkeypatch, name, tmp_path):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    response = client.post("/api/verified-memory/admin/ingest", json={"db_path": str(tmp_path / "vm.sqlite3"), "path": str(tmp_path / name), "confirm_mutation": True})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "unsupported_file_type"


def test_enabled_admin_extract_rejects_allowed_web_search(client, monkeypatch, tmp_path):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    response = client.post("/api/verified-memory/admin/extract-claims", json={"db_path": str(tmp_path / "vm.sqlite3"), "allowed_web_search": True, "confirm_mutation": True})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "web_search_not_allowed"


def test_enabled_admin_ingest_calls_ingest_document_only(client, fake_service, monkeypatch, tmp_path):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    def ingest_document(self, path, *, replace_existing=True):
        self.calls.append(("ingest_document", self.db_path, path, replace_existing))
        return {"operation": "ingest_document", "document_id": "doc_1", "chunk_ids": ["chunk_1"], "chunks_created": 1, "audit": {"llm_called": False, "web_called": False}}
    monkeypatch.setattr(FakeService, "ingest_document", ingest_document, raising=False)
    response = client.post("/api/verified-memory/admin/ingest", json={"db_path": "vm.db", "path": str(doc), "confirm_mutation": True})
    assert response.status_code == 200
    assert fake_service.calls == [("ingest_document", "vm.db", str(doc), True)]
    assert response.json()["payload"]["chunks_created"] == 1


def test_enabled_admin_extract_calls_extract_claims_only(client, fake_service, monkeypatch):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    def extract_claims(self, *, document_id=None, chunk_ids=None, default_sensitivity="private", allowed_web_search=False):
        self.calls.append(("extract_claims", self.db_path, document_id, chunk_ids, default_sensitivity, allowed_web_search))
        return {"operation": "extract_claims", "claim_ids": ["claim_1"], "claims_created": 1, "audit": {"llm_called": False, "web_called": False}}
    monkeypatch.setattr(FakeService, "extract_claims", extract_claims, raising=False)
    response = client.post("/api/verified-memory/admin/extract-claims", json={"db_path": "vm.db", "document_id": "doc_1", "confirm_mutation": True})
    assert response.status_code == 200
    assert fake_service.calls == [("extract_claims", "vm.db", "doc_1", None, "private", False)]
    assert response.json()["payload"]["claims_created"] == 1


def test_enabled_admin_ingest_with_temp_txt_creates_chunks(client, monkeypatch, tmp_path):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    response = client.post("/api/verified-memory/admin/ingest", json={"db_path": str(tmp_path / "vm.sqlite3"), "path": str(doc), "confirm_mutation": True})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["payload"]["chunks_created"] >= 1
    assert body["audit"]["mutation_performed"] is True
    assert body["audit"]["web_called"] is False
    assert body["audit"]["llm_called"] is False


def test_enabled_admin_extract_after_ingest_creates_candidate_claims(client, monkeypatch, tmp_path):
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    doc = tmp_path / "sop.md"
    doc.write_text("- Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    db_path = tmp_path / "vm.sqlite3"
    ingest_response = client.post("/api/verified-memory/admin/ingest", json={"db_path": str(db_path), "path": str(doc), "confirm_mutation": True})
    document_id = ingest_response.json()["payload"]["document_id"]
    response = client.post("/api/verified-memory/admin/extract-claims", json={"db_path": str(db_path), "document_id": document_id, "confirm_mutation": True})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["payload"]["claims_created"] >= 1
    assert body["audit"]["mutation_performed"] is True
    assert body["audit"]["web_called"] is False
    assert body["audit"]["llm_called"] is False


def test_admin_route_responses_are_json_serializable(client, monkeypatch, tmp_path):
    doc = tmp_path / "sop.txt"
    doc.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    responses = [client.post("/api/verified-memory/admin/ingest", json={"db_path": str(tmp_path / "disabled.sqlite3"), "path": str(doc), "confirm_mutation": True}).json()]
    monkeypatch.setenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "true")
    responses.append(client.post("/api/verified-memory/admin/ingest", json={"db_path": str(tmp_path / "enabled.sqlite3"), "path": str(doc), "confirm_mutation": True}).json())
    for body in responses:
        json.dumps(body)


def test_route_source_does_not_call_generation():
    tree = ast.parse(ROUTE_PATH.read_text(encoding="utf-8"))
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    assert "generate_answer" not in called
