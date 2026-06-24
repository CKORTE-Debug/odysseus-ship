from pathlib import Path

DOC_PATH = Path("docs/verified-memory/11_Service_Boundary_and_Integration_Guide.md")


def test_service_boundary_documentation_file_exists():
    assert DOC_PATH.exists()


def test_service_boundary_documentation_mentions_verified_memory_service():
    assert "VerifiedMemoryService" in DOC_PATH.read_text(encoding="utf-8")


def test_service_boundary_documentation_mentions_safe_to_show():
    assert "safe_to_show" in DOC_PATH.read_text(encoding="utf-8")


def test_service_boundary_documentation_mentions_allow_network_llm_defaults_false():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "allow_network_llm" in text
    assert "defaults false" in text


def test_service_boundary_documentation_mentions_no_forbidden_integrations():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "web verification" in text
    assert "search integration" in text
    assert "UI routes" in text
    assert "ChromaDB" in text
