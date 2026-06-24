"""Serializable request/response contracts for verified-memory generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from verified_memory.config import VerifiedMemoryGenerationConfig


@dataclass(frozen=True)
class VerifiedMemoryAnswerRequest:
    question: str
    db_path: str | None = None
    max_chunks: int = 5
    max_claims: int = 5
    include_archived: bool = False
    generation_config: VerifiedMemoryGenerationConfig | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "db_path": self.db_path,
            "max_chunks": self.max_chunks,
            "max_claims": self.max_claims,
            "include_archived": self.include_archived,
            "generation_config": self.generation_config.to_dict() if self.generation_config else None,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class VerifiedMemoryAnswerResponse:
    question: str
    answer: str
    safe_to_show: bool
    validation: dict[str, Any]
    operation: str = "generate_answer"
    validation_severity: str | None = None
    audit: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    prompt_metadata: dict[str, Any] = field(default_factory=dict)
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "safe_to_show": self.safe_to_show,
            "validation": dict(self.validation),
            "operation": self.operation,
            "validation_severity": self.validation_severity,
            "audit": dict(self.audit),
            "warnings": list(self.warnings),
            "prompt_metadata": dict(self.prompt_metadata),
            "generation_metadata": dict(self.generation_metadata),
            "metadata": dict(self.metadata),
        }
