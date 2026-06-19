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

    assert calls == [(prompt.messages, {"model": "fake-model", "temperature": 0.0})]
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
