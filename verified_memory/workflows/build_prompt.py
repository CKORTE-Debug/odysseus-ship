"""Workflow for deterministic verified-memory prompt assembly."""

from __future__ import annotations

from verified_memory.prompting import VerifiedMemoryPrompt, build_verified_memory_prompt
from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows.build_verified_context import build_verified_context


def build_prompt(
    question: str,
    store: SQLiteVerifiedMemoryStore,
    *,
    max_chunks: int = 5,
    max_claims: int = 5,
    include_archived: bool = False,
) -> VerifiedMemoryPrompt:
    """Build verified context and turn it into prompt messages without calling an LLM."""

    context = build_verified_context(
        question,
        store,
        max_chunks=max_chunks,
        max_claims=max_claims,
        include_archived=include_archived,
    )
    return build_verified_memory_prompt(context)
