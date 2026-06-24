"""Controlled answer generation for verified-memory prompts."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from verified_memory.config import VerifiedMemoryGenerationConfig
from verified_memory.prompting import VerifiedMemoryPrompt
from verified_memory.validation import AnswerValidationResult, validate_answer_against_prompt


@dataclass(frozen=True)
class GeneratedAnswerResult:
    """Structured result for a generated verified-memory answer."""

    answer: str
    validation_result: AnswerValidationResult
    prompt_metadata: dict[str, Any]
    warnings: list[str]
    safe_to_show: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "validation_result": self.validation_result.to_dict(),
            "validation": self.validation_result.to_dict(),
            "prompt_metadata": dict(self.prompt_metadata),
            "warnings": list(self.warnings),
            "safe_to_show": self.safe_to_show,
            "metadata": dict(self.metadata),
        }


async def generate_answer_from_prompt(
    prompt: VerifiedMemoryPrompt,
    *,
    config: VerifiedMemoryGenerationConfig | None = None,
    llm_call: Callable[..., Any] | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> GeneratedAnswerResult:
    """Generate and validate one candidate answer from an existing safe prompt."""

    if config is None:
        config = (
            VerifiedMemoryGenerationConfig(model=model or "", temperature=0.0 if temperature is None else temperature)
            if llm_call is not None
            else VerifiedMemoryGenerationConfig.from_env()
        )
    elif model is not None or temperature is not None:
        config = VerifiedMemoryGenerationConfig(
            model=model if model is not None else config.model,
            endpoint_url=config.endpoint_url,
            temperature=temperature if temperature is not None else config.temperature,
            max_tokens=config.max_tokens,
            timeout_seconds=config.timeout_seconds,
            allow_network_llm=config.allow_network_llm,
            provider=config.provider,
            metadata=dict(config.metadata),
        )

    config.validate(llm_call_provided=llm_call is not None)
    warnings = list(prompt.warnings)
    metadata: dict[str, Any] = {
        "llm_called": False,
        "web_called": False,
        "generation_model": config.model or None,
        "provider": config.provider,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout_seconds": config.timeout_seconds,
        "allow_network_llm": config.allow_network_llm,
        "config_validated": True,
    }

    if llm_call is None:
        from src.llm_core import llm_call_async as odysseus_llm_call_async

        async def default_llm_call(messages: list[dict[str, str]], **kwargs: Any) -> str:
            return await odysseus_llm_call_async(
                config.endpoint_url,
                kwargs["model"],
                messages,
                temperature=kwargs["temperature"],
            )

        llm_call = default_llm_call

    metadata["llm_called"] = True
    try:
        raw_answer = llm_call(prompt.messages, model=config.model or None, temperature=config.temperature, max_tokens=config.max_tokens, timeout_seconds=config.timeout_seconds)
        answer = await raw_answer if inspect.isawaitable(raw_answer) else raw_answer
    except Exception:
        metadata["generation_failed"] = True
        raise

    answer_text = str(answer or "")
    validation_result = validate_answer_against_prompt(prompt, answer_text)
    safe_to_show = validation_result.severity in {"pass", "warning"}
    metadata.update(
        {
            "validation_severity": validation_result.severity,
            "validation_issue_codes": [issue.code for issue in validation_result.issues],
        }
    )
    prompt_metadata = {**dict(prompt.metadata), "answer_generated": True, "online_verification_performed": False}
    return GeneratedAnswerResult(
        answer=answer_text,
        validation_result=validation_result,
        prompt_metadata=prompt_metadata,
        warnings=warnings,
        safe_to_show=safe_to_show,
        metadata=metadata,
    )
