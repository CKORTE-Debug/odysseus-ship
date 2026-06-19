"""Workflow for controlled verified-memory answer generation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from verified_memory.generation import GeneratedAnswerResult, generate_answer_from_prompt
from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows.build_prompt import build_prompt


async def generate_answer(
    question: str,
    store: SQLiteVerifiedMemoryStore,
    *,
    max_chunks: int = 5,
    max_claims: int = 5,
    include_archived: bool = False,
    model: str | None = None,
    temperature: float = 0.0,
    llm_call: Callable[..., Any] | None = None,
) -> GeneratedAnswerResult:
    """Build a prompt, generate one candidate answer, and validate it."""

    prompt = build_prompt(
        question,
        store,
        max_chunks=max_chunks,
        max_claims=max_claims,
        include_archived=include_archived,
    )
    return await generate_answer_from_prompt(
        prompt,
        llm_call=llm_call,
        model=model,
        temperature=temperature,
    )
