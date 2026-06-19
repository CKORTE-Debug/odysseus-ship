"""Controlled answer generation for verified-memory prompts."""

from __future__ import annotations

import inspect
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

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
    llm_call: Callable[..., Any] | None = None,
    model: str | None = None,
    temperature: float = 0.0,
) -> GeneratedAnswerResult:
    """Generate and validate one candidate answer from an existing safe prompt."""

    selected_model = model or os.getenv("VERIFIED_MEMORY_LLM_MODEL") or os.getenv("LLM_MODEL") or ""
    warnings = list(prompt.warnings)
    metadata: dict[str, Any] = {
        "llm_called": False,
        "web_called": False,
        "generation_model": selected_model or None,
        "temperature": temperature,
    }

    if llm_call is None:
        endpoint_url = os.getenv("VERIFIED_MEMORY_LLM_URL") or os.getenv("LLM_ENDPOINT_URL") or os.getenv("LLM_URL")
        if not endpoint_url or not selected_model:
            raise ValueError(
                "verified-memory answer generation requires llm_call injection or VERIFIED_MEMORY_LLM_URL/LLM_ENDPOINT_URL "
                "and VERIFIED_MEMORY_LLM_MODEL/LLM_MODEL environment variables"
            )
        from src.llm_core import llm_call_async as odysseus_llm_call_async

        async def default_llm_call(messages: list[dict[str, str]], **kwargs: Any) -> str:
            return await odysseus_llm_call_async(endpoint_url, kwargs["model"], messages, temperature=kwargs["temperature"])

        llm_call = default_llm_call

    metadata["llm_called"] = True
    try:
        raw_answer = llm_call(prompt.messages, model=selected_model or model, temperature=temperature)
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
