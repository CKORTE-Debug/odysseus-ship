"""Verified-memory API routes.

This router is intentionally conservative: it exposes deterministic read-only
service-boundary operations plus tightly gated admin write operations. It does
not import legacy memory, LLM, search/research, ChromaDB, ingestion, extraction,
or generation modules.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from verified_memory.contracts import VerifiedMemoryServiceEnvelope
from verified_memory.service import VerifiedMemoryService, VerifiedMemoryServiceError


class _ReadOnlyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1)
    db_path: str | None = None
    max_chunks: int = Field(default=5, ge=0)
    max_claims: int = Field(default=5, ge=0)
    include_archived: bool = False


class VerifiedMemoryContextRequest(_ReadOnlyRequest):
    """Request body for deterministic context retrieval."""


class VerifiedMemoryPromptRequest(_ReadOnlyRequest):
    """Request body for deterministic prompt construction."""


class VerifiedMemoryValidateAnswerRequest(_ReadOnlyRequest):
    """Request body for deterministic answer validation."""

    answer: str = Field(..., min_length=1)


class VerifiedMemoryIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    db_path: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    replace_existing: bool = True
    confirm_mutation: bool = False


class VerifiedMemoryExtractClaimsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    db_path: str = Field(..., min_length=1)
    document_id: str | None = None
    chunk_ids: list[str] | None = None
    default_sensitivity: str = "private"
    allowed_web_search: bool = False
    confirm_mutation: bool = False


_CAPABILITIES: dict[str, bool] = {
    "build_context": True,
    "build_prompt": True,
    "validate_answer": True,
    "generate_answer": False,
    "admin_routes_enabled": False,
    "ingest_document": False,
    "extract_claims": False,
    "web_verification": False,
    "chromadb": False,
    "legacy_memory_mutation": False,
}


def _service_from_request(db_path: str | None, *, operation: str) -> VerifiedMemoryService:
    if not db_path:
        raise HTTPException(
            status_code=400,
            detail=_failure(
                operation,
                "missing_db_path",
                "db_path is required because no verified-memory API default database path is configured.",
            ),
        )
    return VerifiedMemoryService.from_db_path(db_path)


def _envelope(payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
    return VerifiedMemoryServiceEnvelope.success(
        operation,
        payload,
        audit=dict(payload.get("audit", {})),
        metadata={"service_boundary": "VerifiedMemoryService", "read_only": True},
    ).to_dict()


def _admin_routes_enabled() -> bool:
    return os.getenv("VERIFIED_MEMORY_ENABLE_ADMIN_ROUTES", "").strip().lower() in {"true", "1", "yes"}


def _capabilities() -> dict[str, bool]:
    capabilities = dict(_CAPABILITIES)
    enabled = _admin_routes_enabled()
    capabilities["admin_routes_enabled"] = enabled
    capabilities["ingest_document"] = enabled
    capabilities["extract_claims"] = enabled
    return capabilities


_SERVICE_ERROR_CODES = {
    "build_context": "context_failed",
    "build_prompt": "prompt_failed",
    "validate_answer": "validate_answer_failed",
    "admin_ingest_document": "ingest_document_failed",
    "admin_extract_claims": "extract_claims_failed",
}


def _failure(operation: str, code: str, message: str, *, mutation_attempted: bool = False, audit: dict[str, Any] | None = None) -> dict[str, Any]:
    error_audit = {
        "operation": operation,
        "mutation_attempted": mutation_attempted,
        "mutation_performed": False,
        "web_called": False,
        "llm_called": False,
    }
    error_audit.update(audit or {})
    error_audit["operation"] = operation
    return VerifiedMemoryServiceEnvelope.failure(
        operation,
        {"code": code, "message": message},
        audit=error_audit,
        metadata={"service_boundary": "VerifiedMemoryService"},
    ).to_dict()


def _service_failure(operation: str, exc: VerifiedMemoryServiceError, *, mutation_attempted: bool = False) -> dict[str, Any]:
    return _failure(
        operation,
        _SERVICE_ERROR_CODES[operation],
        str(exc),
        mutation_attempted=mutation_attempted,
        audit=dict(getattr(exc, "audit", {})),
    )


def _admin_disabled(operation: str) -> dict[str, Any]:
    return _failure(operation, "admin_routes_disabled", "Verified-memory admin routes are disabled.")


def _validate_local_text_path(path: str, *, operation: str) -> None:
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        raise HTTPException(status_code=400, detail=_failure(operation, "invalid_path", "path must be a local .txt or .md file path.", mutation_attempted=True))
    suffix = Path(path).suffix.lower()
    if suffix not in {".txt", ".md"}:
        raise HTTPException(status_code=400, detail=_failure(operation, "unsupported_file_type", "Only local .txt and .md documents are supported.", mutation_attempted=True))


def _require_confirmation(confirm_mutation: bool, *, operation: str) -> None:
    if confirm_mutation is not True:
        raise HTTPException(status_code=400, detail=_failure(operation, "mutation_not_confirmed", "confirm_mutation must be true for verified-memory admin write routes.", mutation_attempted=True))


def _admin_envelope(payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
    audit = {
        "operation": operation,
        "mutation_attempted": True,
        "mutation_performed": True,
        "web_called": False,
        "llm_called": False,
        **dict(payload.get("audit", {})),
    }
    audit["operation"] = operation
    audit["mutation_attempted"] = True
    audit["mutation_performed"] = True
    audit["web_called"] = False
    audit["llm_called"] = False
    return VerifiedMemoryServiceEnvelope.success(
        operation,
        payload,
        audit=audit,
        metadata={"service_boundary": "VerifiedMemoryService", "admin_write": True},
    ).to_dict()


def setup_verified_memory_routes() -> APIRouter:
    router = APIRouter(prefix="/api/verified-memory", tags=["verified-memory"])

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "operation": "verified_memory_health",
            "ok": True,
            "capabilities": _capabilities(),
        }

    @router.post("/context")
    async def build_context(request: VerifiedMemoryContextRequest) -> dict[str, Any]:
        operation = "build_context"
        service = _service_from_request(request.db_path, operation=operation)
        try:
            payload = service.build_context(
                request.question,
                max_chunks=request.max_chunks,
                max_claims=request.max_claims,
                include_archived=request.include_archived,
            )
        except VerifiedMemoryServiceError as exc:
            raise HTTPException(status_code=400, detail=_service_failure(operation, exc)) from exc
        return _envelope(payload, operation=operation)

    @router.post("/prompt")
    async def build_prompt(request: VerifiedMemoryPromptRequest) -> dict[str, Any]:
        operation = "build_prompt"
        service = _service_from_request(request.db_path, operation=operation)
        try:
            payload = service.build_prompt(
                request.question,
                max_chunks=request.max_chunks,
                max_claims=request.max_claims,
                include_archived=request.include_archived,
            )
        except VerifiedMemoryServiceError as exc:
            raise HTTPException(status_code=400, detail=_service_failure(operation, exc)) from exc
        return _envelope(payload, operation=operation)

    @router.post("/validate-answer")
    async def validate_answer(request: VerifiedMemoryValidateAnswerRequest) -> dict[str, Any]:
        operation = "validate_answer"
        service = _service_from_request(request.db_path, operation=operation)
        try:
            payload = service.validate_answer(
                request.question,
                request.answer,
                max_chunks=request.max_chunks,
                max_claims=request.max_claims,
                include_archived=request.include_archived,
            )
        except VerifiedMemoryServiceError as exc:
            raise HTTPException(status_code=400, detail=_service_failure(operation, exc)) from exc
        return _envelope(payload, operation=operation)


    @router.post("/admin/ingest")
    async def admin_ingest_document(request: VerifiedMemoryIngestRequest) -> dict[str, Any]:
        operation = "admin_ingest_document"
        if not _admin_routes_enabled():
            raise HTTPException(status_code=403, detail=_admin_disabled(operation))
        _require_confirmation(request.confirm_mutation, operation=operation)
        _validate_local_text_path(request.path, operation=operation)
        service = _service_from_request(request.db_path, operation=operation)
        try:
            payload = service.ingest_document(request.path, replace_existing=request.replace_existing)
        except VerifiedMemoryServiceError as exc:
            raise HTTPException(status_code=400, detail=_service_failure(operation, exc, mutation_attempted=True)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=_failure(operation, "ingest_document_failed", str(exc), mutation_attempted=True)) from exc
        return _admin_envelope(payload, operation=operation)

    @router.post("/admin/extract-claims")
    async def admin_extract_claims(request: VerifiedMemoryExtractClaimsRequest) -> dict[str, Any]:
        operation = "admin_extract_claims"
        if not _admin_routes_enabled():
            raise HTTPException(status_code=403, detail=_admin_disabled(operation))
        _require_confirmation(request.confirm_mutation, operation=operation)
        if request.allowed_web_search is True:
            raise HTTPException(status_code=400, detail=_failure(operation, "web_search_not_allowed", "allowed_web_search must remain false for route-based claim extraction.", mutation_attempted=True))
        if request.default_sensitivity not in {"private", "public"}:
            raise HTTPException(status_code=400, detail=_failure(operation, "invalid_sensitivity", "default_sensitivity must be private or public.", mutation_attempted=True))
        service = _service_from_request(request.db_path, operation=operation)
        try:
            payload = service.extract_claims(
                document_id=request.document_id,
                chunk_ids=request.chunk_ids,
                default_sensitivity=request.default_sensitivity,
                allowed_web_search=False,
            )
        except VerifiedMemoryServiceError as exc:
            raise HTTPException(status_code=400, detail=_service_failure(operation, exc, mutation_attempted=True)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=_failure(operation, "extract_claims_failed", str(exc), mutation_attempted=True)) from exc
        return _admin_envelope(payload, operation=operation)

    return router
