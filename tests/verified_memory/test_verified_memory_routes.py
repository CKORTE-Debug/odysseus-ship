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
    forbidden_calls = {"generate_answer", "ingest_document", "extract_claims", "web_search", "research", "ChromaDB"}
    assert forbidden_imports.isdisjoint(imported)
    assert forbidden_calls.isdisjoint(called)
