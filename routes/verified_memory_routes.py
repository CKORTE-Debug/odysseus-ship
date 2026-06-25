"""Read-only verified-memory API routes.

This router is intentionally conservative: it exposes only deterministic,
read-only service-boundary operations and does not import legacy memory, LLM,
search/research, ChromaDB, ingestion, extraction, or generation modules.
"""

from __future__ import annotations

from typing import Any

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


_CAPABILITIES: dict[str, bool] = {
    "build_context": True,
    "build_prompt": True,
    "validate_answer": True,
    "generate_answer": False,
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
            detail=VerifiedMemoryServiceEnvelope.failure(
                operation,
                {
                    "code": "missing_db_path",
                    "message": "db_path is required because no verified-memory API default database path is configured.",
                },
                audit={"operation": operation},
                metadata={"service_boundary": "VerifiedMemoryService"},
            ).to_dict(),
        )
    return VerifiedMemoryService.from_db_path(db_path)


def _envelope(payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
    return VerifiedMemoryServiceEnvelope.success(
        operation,
        payload,
        audit=dict(payload.get("audit", {})),
        metadata={"service_boundary": "VerifiedMemoryService", "read_only": True},
    ).to_dict()


def setup_verified_memory_routes() -> APIRouter:
    router = APIRouter(prefix="/api/verified-memory", tags=["verified-memory"])

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "operation": "verified_memory_health",
            "ok": True,
            "capabilities": dict(_CAPABILITIES),
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
            raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
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
            raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
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
            raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
        return _envelope(payload, operation=operation)

    return router
