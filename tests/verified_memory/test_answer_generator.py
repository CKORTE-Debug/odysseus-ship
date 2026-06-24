import pytest

from verified_memory.generation import generate_answer_from_prompt
from verified_memory.prompting import VerifiedMemoryPrompt


def _prompt():
    return VerifiedMemoryPrompt(
        system_message="system",
        user_message="user",
        evidence_blocks={
            "usable_verified_claims": [{"claim": "Users must connect to Wi-Fi.", "source_refs": ["doc-1:chunk:0001"]}],
            "local_evidence_chunks": [],
            "not_confirmed_claims": [],
            "citation_source_refs": ["doc-1:chunk:0001"],
        },
        warnings=[],
        metadata={"answer_generated": False, "online_verification_performed": False},
    )


@pytest.mark.asyncio
async def test_answer_generator_calls_provided_fake_with_prompt_messages():
    prompt = _prompt()
    calls = []

    async def fake_llm(messages, **kwargs):
        calls.append((messages, kwargs))
        return "Users must connect to Wi-Fi. [doc-1:chunk:0001]"

    result = await generate_answer_from_prompt(prompt, llm_call=fake_llm, model="fake-model", temperature=0.0)

    assert calls == [(prompt.messages, {"model": "fake-model", "temperature": 0.0, "max_tokens": None, "timeout_seconds": None})]
    assert result.safe_to_show is True
    assert result.validation_result.severity == "pass"
    assert result.metadata["llm_called"] is True
    assert result.metadata["web_called"] is False


@pytest.mark.asyncio
async def test_generated_answer_with_allowed_citation_passes_validation():
    async def fake_llm(messages, **kwargs):
        return "Users must connect to Wi-Fi. [doc-1:chunk:0001]"

    result = await generate_answer_from_prompt(_prompt(), llm_call=fake_llm)

    assert result.safe_to_show is True
    assert result.validation_result.is_valid is True
    assert result.validation_result.severity == "pass"


@pytest.mark.asyncio
async def test_generated_answer_with_invented_citation_is_unsafe():
    async def fake_llm(messages, **kwargs):
        return "Users must connect to Wi-Fi. [doc-9:chunk:9999]"

    result = await generate_answer_from_prompt(_prompt(), llm_call=fake_llm)

    assert result.safe_to_show is False
    assert result.validation_result.severity == "error"
    assert result.validation_result.issues[0].code == "invented_citation"
    assert result.answer == "Users must connect to Wi-Fi. [doc-9:chunk:9999]"


@pytest.mark.asyncio
async def test_generated_answer_claiming_online_verification_is_unsafe():
    async def fake_llm(messages, **kwargs):
        return "I checked online and confirmed this. [doc-1:chunk:0001]"

    result = await generate_answer_from_prompt(_prompt(), llm_call=fake_llm)

    assert result.safe_to_show is False
    assert result.validation_result.severity == "error"
    assert [issue.code for issue in result.validation_result.issues] == ["false_online_verification_claim"]


@pytest.mark.asyncio
async def test_generated_answer_missing_citation_warns_but_is_safe_to_show():
    async def fake_llm(messages, **kwargs):
        return "Users must connect to Wi-Fi."

    result = await generate_answer_from_prompt(_prompt(), llm_call=fake_llm)

    assert result.safe_to_show is True
    assert result.validation_result.severity == "warning"
    assert result.validation_result.issues[0].code == "missing_citation"

@pytest.mark.asyncio
async def test_invalid_config_fails_before_importing_llm_core(monkeypatch):
    import sys
    from verified_memory.config import VerifiedMemoryGenerationConfig

    sys.modules.pop("src.llm_core", None)
    with pytest.raises(ValueError, match="allow_network_llm"):
        await generate_answer_from_prompt(_prompt(), config=VerifiedMemoryGenerationConfig(model="m"))
    assert "src.llm_core" not in sys.modules


@pytest.mark.asyncio
async def test_injected_fake_llm_call_works_without_endpoint_and_does_not_import_llm_core(monkeypatch):
    import sys
    from verified_memory.config import VerifiedMemoryGenerationConfig

    sys.modules.pop("src.llm_core", None)

    async def fake_llm(messages, **kwargs):
        return "Users must connect to Wi-Fi. [doc-1:chunk:0001]"

    result = await generate_answer_from_prompt(
        _prompt(),
        config=VerifiedMemoryGenerationConfig(model="fake-model"),
        llm_call=fake_llm,
    )

    assert result.safe_to_show is True
    assert result.metadata["config_validated"] is True
    assert "src.llm_core" not in sys.modules


@pytest.mark.asyncio
async def test_real_fallback_imports_llm_core_only_after_valid_network_config(monkeypatch):
    import sys
    import types
    from verified_memory.config import VerifiedMemoryGenerationConfig

    sys.modules.pop("src.llm_core", None)
    calls = []
    module = types.ModuleType("src.llm_core")

    async def fake_core(endpoint_url, model, messages, **kwargs):
        calls.append((endpoint_url, model, messages, kwargs))
        return "Users must connect to Wi-Fi. [doc-1:chunk:0001]"

    module.llm_call_async = fake_core
    monkeypatch.setitem(sys.modules, "src.llm_core", module)

    result = await generate_answer_from_prompt(
        _prompt(),
        config=VerifiedMemoryGenerationConfig(
            model="real-model",
            endpoint_url="http://localhost:11434",
            allow_network_llm=True,
        ),
    )

    assert result.safe_to_show is True
    assert calls[0][0] == "http://localhost:11434"
    assert calls[0][1] == "real-model"
    assert calls[0][2] == _prompt().messages


@pytest.mark.asyncio
async def test_generation_metadata_includes_validation_details():
    async def fake_llm(messages, **kwargs):
        return "Users must connect to Wi-Fi. [made-up:chunk:9999]"

    result = await generate_answer_from_prompt(_prompt(), llm_call=fake_llm)

    assert result.safe_to_show is False
    assert result.metadata["validation_severity"] == "error"
    assert result.metadata["validation_issue_codes"] == ["invented_citation"]
