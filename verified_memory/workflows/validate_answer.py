"""Workflow for validating manually provided answers against verified-memory prompts."""

from __future__ import annotations

from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.validation import AnswerValidationResult, validate_answer_against_prompt
from verified_memory.workflows.build_prompt import build_prompt


def validate_answer(
    question: str,
    answer: str,
    store: SQLiteVerifiedMemoryStore,
    *,
    max_chunks: int = 5,
    max_claims: int = 5,
    include_archived: bool = False,
) -> AnswerValidationResult:
    """Build a prompt and validate a candidate answer without generating an answer."""

    prompt = build_prompt(
        question,
        store,
        max_chunks=max_chunks,
        max_claims=max_claims,
        include_archived=include_archived,
    )
    return validate_answer_against_prompt(prompt, answer)
