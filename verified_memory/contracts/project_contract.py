"""Versioned, transport-independent contracts shared by companion modules.

Only an authenticated adapter may construct RequestScope. Source text is data,
never a grant of tool authority. Character budgets are deliberately not called
token budgets: provider tokenization belongs to the model adapter.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from verified_memory.errors import InvalidRecordError

CONTRACT_VERSION = "1.0"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_CHARS = 64_000


@dataclass(frozen=True)
class RequestScope:
    actor_id: str
    project_id: str

    def __post_init__(self) -> None:
        if not self.actor_id.strip() or len(self.actor_id) > 256:
            raise InvalidRecordError("An authenticated actor is required")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", self.project_id):
            raise InvalidRecordError("Invalid project ID")


@dataclass(frozen=True)
class SourceInput:
    filename: str
    text: str
    source_key: str | None = None
    source_url: str | None = None
    external_revision: str | None = None
    effective_from: str | None = None
    authority: str = "reference"
    canonical_role: str | None = None
    owner_approved: bool = False
    sensitivity: str = "private"


@dataclass(frozen=True)
class EvidenceQuery:
    question: str
    limit: int = 5
    context_budget_chars: int = 12_000
    as_of: str | None = None

    def __post_init__(self) -> None:
        if not self.question.strip() or len(self.question) > 4_000:
            raise InvalidRecordError("Question must contain 1–4000 characters")
        if not 1 <= self.limit <= 20:
            raise InvalidRecordError("Evidence limit must be between 1 and 20")
        if not 256 <= self.context_budget_chars <= MAX_CONTEXT_CHARS:
            raise InvalidRecordError("Context budget must be between 256 and 64000 characters")


@dataclass(frozen=True)
class SourceRevision:
    revision_id: str
    source_key: str
    filename: str
    content_sha256: str
    imported_at: str
    effective_from: str
    authority: str
    canonical_role: str | None
    owner_approved: bool
    sensitivity: str
    source_url: str | None
    external_revision: str | None
    text: str

    def to_dict(self, *, include_text: bool = False) -> dict[str, Any]:
        result = asdict(self)
        if not include_text:
            result.pop("text")
        return result


@dataclass(frozen=True)
class EvidencePassage:
    citation_ref: str
    source: SourceRevision
    text: str
    line_start: int
    line_end: int
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "citation_ref": self.citation_ref,
            "source": self.source.to_dict(),
            "text": self.text,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "score": self.score,
            "citation_integrity": "source_linked",
            "claim_support": "not_evaluated",
        }


@dataclass(frozen=True)
class EvidenceBundle:
    scope: RequestScope
    query: EvidenceQuery
    passages: tuple[EvidencePassage, ...]
    warnings: tuple[str, ...] = ()
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "scope": asdict(self.scope),
            "query": asdict(self.query),
            "passages": [p.to_dict() for p in self.passages],
            "warnings": list(self.warnings),
            "claim_support": "not_evaluated",
            "remote_calls": False,
        }


@dataclass(frozen=True)
class PreparedTaskContext:
    scope: RequestScope
    generated_at: str
    required_sources: tuple[SourceRevision, ...]
    evidence: EvidenceBundle
    max_age_seconds: int
    project_fingerprint: str
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "scope": asdict(self.scope),
            "generated_at": self.generated_at,
            "required_sources": [s.to_dict(include_text=True) for s in self.required_sources],
            "evidence": self.evidence.to_dict(),
            "max_age_seconds": self.max_age_seconds,
            "project_fingerprint": self.project_fingerprint,
            "freshness": "local_import_age_checked",
            "live_upstream_revision_checked": False,
        }


class MemoryPort(Protocol):
    def prepare_task_context(
        self, query: EvidenceQuery, *, max_age_seconds: int = 86_400,
        expected_revisions: dict[str, str] | None = None,
    ) -> PreparedTaskContext: ...

    def assert_context_current(self, context: PreparedTaskContext) -> None: ...

    def validate_context_answer(self, context: PreparedTaskContext, answer: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ModelCall:
    task_id: str
    context: PreparedTaskContext
    provider_id: str
    max_output_chars: int = 12_000


class ModelPort(Protocol):
    async def generate(self, request: ModelCall) -> str: ...


class CheckpointPort(Protocol):
    def save(
        self, scope: RequestScope, task_id: str, payload: dict[str, Any],
        *, expected_version: int,
    ) -> int: ...

    def load(self, scope: RequestScope, task_id: str) -> tuple[int, dict[str, Any]]: ...
