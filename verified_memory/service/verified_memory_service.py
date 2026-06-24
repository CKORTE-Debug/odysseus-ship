"""App-facing service boundary for verified-memory operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from verified_memory.contracts import (
    VerifiedMemoryAnswerRequest,
    VerifiedMemoryAnswerResponse,
    VerifiedMemoryServiceEnvelope,
)
from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows.build_prompt import build_prompt as build_prompt_workflow
from verified_memory.workflows.build_verified_context import build_verified_context as build_context_workflow
from verified_memory.workflows.extract_claims import extract_claims as extract_claims_workflow
from verified_memory.workflows.generate_answer import generate_answer as generate_answer_workflow
from verified_memory.workflows.ingest_document import ingest_document as ingest_document_workflow
from verified_memory.workflows.validate_answer import validate_answer as validate_answer_workflow


class VerifiedMemoryServiceError(Exception):
    """Deterministic service-boundary error that avoids exposing stack traces."""

    def __init__(self, message: str, *, operation: str, audit: dict[str, Any] | None = None):
        super().__init__(message)
        self.operation = operation
        self.audit = {"operation": operation, **(audit or {})}

    def to_dict(self) -> dict[str, Any]:
        return {"operation": self.operation, "error": str(self), "audit": dict(self.audit)}


class VerifiedMemoryService:
    """Thin controlled adapter over verified-memory workflows."""

    def __init__(self, store: SQLiteVerifiedMemoryStore):
        self.store = store

    @classmethod
    def from_db_path(cls, path: str | Path) -> "VerifiedMemoryService":
        return cls(SQLiteVerifiedMemoryStore(path))

    def envelope(self, payload: dict[str, Any], *, operation: str) -> VerifiedMemoryServiceEnvelope:
        return VerifiedMemoryServiceEnvelope.success(
            operation,
            payload,
            audit=dict(payload.get("audit", {})),
            metadata={"service_boundary": "VerifiedMemoryService"},
        )

    def ingest_document(self, path: str | Path, *, replace_existing: bool = True) -> dict[str, Any]:
        operation = "ingest_document"
        result = ingest_document_workflow(path, self.store, replace_existing=replace_existing)
        payload = result.__dict__.copy()
        return {**payload, "operation": operation, "audit": self._audit(operation, safe_to_show=True)}

    def extract_claims(
        self,
        *,
        document_id: str | None = None,
        chunk_ids: list[str] | None = None,
        default_sensitivity: str = "private",
        allowed_web_search: bool = False,
    ) -> dict[str, Any]:
        operation = "extract_claims"
        result = extract_claims_workflow(
            self.store,
            document_id=document_id,
            chunk_ids=chunk_ids,
            default_sensitivity=default_sensitivity,
            allowed_web_search=allowed_web_search,
        )
        payload = result.__dict__.copy()
        return {**payload, "operation": operation, "audit": self._audit(operation, safe_to_show=True, web_called=False)}

    def build_context(
        self,
        question: str,
        *,
        max_chunks: int = 5,
        max_claims: int = 5,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        operation = "build_context"
        package = build_context_workflow(
            question,
            self.store,
            max_chunks=max_chunks,
            max_claims=max_claims,
            include_archived=include_archived,
        )
        return {**package.to_dict(), "operation": operation, "audit": self._audit(operation, safe_to_show=True)}

    def build_prompt(
        self,
        question: str,
        *,
        max_chunks: int = 5,
        max_claims: int = 5,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        operation = "build_prompt"
        prompt = build_prompt_workflow(
            question,
            self.store,
            max_chunks=max_chunks,
            max_claims=max_claims,
            include_archived=include_archived,
        )
        return {**prompt.to_dict(), "operation": operation, "audit": self._audit(operation, safe_to_show=True)}

    def validate_answer(
        self,
        question: str,
        answer: str,
        *,
        max_chunks: int = 5,
        max_claims: int = 5,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        operation = "validate_answer"
        result = validate_answer_workflow(
            question,
            answer,
            self.store,
            max_chunks=max_chunks,
            max_claims=max_claims,
            include_archived=include_archived,
        )
        safe_to_show = result.severity != "error"
        return {
            "operation": operation,
            "validation": result.to_dict(),
            "validation_status": result.severity,
            "validation_severity": result.severity,
            "safe_to_show": safe_to_show,
            "audit": self._audit(
                operation,
                answer_validated=True,
                safe_to_show=safe_to_show,
                validation_severity=result.severity,
                validation_issue_codes=[issue.code for issue in result.issues],
            ),
        }

    async def generate_answer(self, request: VerifiedMemoryAnswerRequest, *, llm_call: Any = None) -> VerifiedMemoryAnswerResponse:
        operation = "generate_answer"
        try:
            result = await generate_answer_workflow(
                request.question,
                self.store,
                max_chunks=request.max_chunks,
                max_claims=request.max_claims,
                include_archived=request.include_archived,
                config=request.generation_config,
                llm_call=llm_call,
            )
        except ValueError as exc:
            raise VerifiedMemoryServiceError(
                f"{operation} failed validation: {exc}",
                operation=operation,
                audit=self._audit(operation, config_validated=False, llm_called=False, answer_validated=False, safe_to_show=False),
            ) from exc

        validation = result.validation_result.to_dict()
        validation_severity = result.validation_result.severity
        issue_codes = [issue.code for issue in result.validation_result.issues]
        safe_to_show = result.safe_to_show and validation_severity != "error"
        audit = self._audit(
            operation,
            llm_called=bool(result.metadata.get("llm_called", False)),
            allow_network_llm=bool(result.metadata.get("allow_network_llm", False)),
            config_validated=bool(result.metadata.get("config_validated", False)),
            answer_validated=True,
            safe_to_show=safe_to_show,
            validation_severity=validation_severity,
            validation_issue_codes=issue_codes,
        )
        return VerifiedMemoryAnswerResponse(
            question=request.question,
            answer=result.answer,
            safe_to_show=safe_to_show,
            validation=validation,
            warnings=list(result.warnings),
            prompt_metadata=dict(result.prompt_metadata),
            generation_metadata=dict(result.metadata),
            operation=operation,
            validation_severity=validation_severity,
            audit=audit,
            metadata={"request_metadata": dict(request.metadata)},
        )

    @staticmethod
    def _audit(
        operation: str,
        *,
        llm_called: bool = False,
        web_called: bool = False,
        allow_network_llm: bool = False,
        config_validated: bool = False,
        answer_validated: bool = False,
        safe_to_show: bool = False,
        validation_severity: str | None = None,
        validation_issue_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "operation": operation,
            "llm_called": llm_called,
            "web_called": web_called,
            "allow_network_llm": allow_network_llm,
            "config_validated": config_validated,
            "answer_validated": answer_validated,
            "safe_to_show": safe_to_show,
            "validation_status": validation_severity,
            "validation_severity": validation_severity,
            "validation_issue_codes": list(validation_issue_codes or []),
        }
