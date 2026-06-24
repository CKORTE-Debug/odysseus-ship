import pytest

from verified_memory.config import VerifiedMemoryGenerationConfig


def test_generation_config_validates_temperature_range():
    with pytest.raises(ValueError, match="temperature"):
        VerifiedMemoryGenerationConfig(temperature=-0.1).validate(llm_call_provided=True)
    with pytest.raises(ValueError, match="temperature"):
        VerifiedMemoryGenerationConfig(temperature=1.1).validate(llm_call_provided=True)


def test_generation_config_rejects_empty_model_when_real_llm_required():
    with pytest.raises(ValueError, match="model"):
        VerifiedMemoryGenerationConfig(endpoint_url="http://localhost", allow_network_llm=True).validate()


def test_generation_config_rejects_missing_endpoint_when_real_llm_required():
    with pytest.raises(ValueError, match="endpoint_url"):
        VerifiedMemoryGenerationConfig(model="local", allow_network_llm=True).validate()


def test_allow_network_llm_defaults_false():
    assert VerifiedMemoryGenerationConfig().allow_network_llm is False


def test_from_env_does_not_allow_network_llm_unless_explicit(monkeypatch):
    monkeypatch.delenv("VERIFIED_MEMORY_ALLOW_NETWORK_LLM", raising=False)
    assert VerifiedMemoryGenerationConfig.from_env().allow_network_llm is False
    monkeypatch.setenv("VERIFIED_MEMORY_ALLOW_NETWORK_LLM", "yes")
    assert VerifiedMemoryGenerationConfig.from_env().allow_network_llm is True
    monkeypatch.setenv("VERIFIED_MEMORY_ALLOW_NETWORK_LLM", "0")
    assert VerifiedMemoryGenerationConfig.from_env().allow_network_llm is False


def test_config_to_dict_does_not_expand_permissions():
    data = VerifiedMemoryGenerationConfig(model="m", endpoint_url="u", allow_network_llm=True).to_dict()
    assert data["allow_network_llm"] is True
    assert data["permissions"] == {"web": False, "search": False, "research": False, "chromadb": False, "ui": False}
