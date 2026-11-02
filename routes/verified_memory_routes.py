"""Authenticated v2 project API over VerifiedMemoryService.

HTTP accepts uploaded text, never database or filesystem paths. Standalone
CLI paths remain a separate local operator interface.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from core.middleware import require_admin
from src.auth_helpers import require_user
from verified_memory.contracts import VerifiedMemoryServiceEnvelope
from verified_memory.contracts.project_contract import (
    CONTRACT_VERSION,
    EvidenceQuery,
    RequestScope,
    SourceInput,
)
from verified_memory.errors import (
    ContextNotReadyError,
    RecordNotFoundError,
    VerifiedMemoryError,
)
from verified_memory.service import VerifiedMemoryService, VerifiedMemoryWorkspace


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ProjectRequest(_StrictRequest):
    project_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')


class QueryRequest(_StrictRequest):
    question: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=20)
    context_budget_chars: int = Field(default=12_000, ge=256, le=64_000)
    as_of: str | None = None

    def query(self) -> EvidenceQuery:
        return EvidenceQuery(**self.model_dump())


class PrepareRequest(QueryRequest):
    max_age_seconds: int = Field(default=86_400, ge=1, le=2_592_000)
    expected_revisions: dict[str, str] = Field(default_factory=dict, max_length=100)

    def query(self) -> EvidenceQuery:
        return EvidenceQuery(**self.model_dump(exclude={'max_age_seconds', 'expected_revisions'}))


class SourceRequest(_StrictRequest):
    filename: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=2 * 1024 * 1024)
    source_key: str | None = Field(default=None, max_length=256)
    source_url: str | None = Field(default=None, max_length=2048)
    external_revision: str | None = Field(default=None, max_length=256)
    effective_from: str | None = None
    authority: str = 'reference'
    canonical_role: str | None = None
    owner_approved: bool = False
    sensitivity: str = 'private'


class _ReadOnlyRequest(_StrictRequest):
    project_id: str = Field(default='default', min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=4000)
    max_chunks: int = Field(default=5, ge=1, le=20)
    max_claims: int = Field(default=5, ge=0, le=20)
    include_archived: bool = False


class VerifiedMemoryValidateAnswerRequest(_ReadOnlyRequest):
    answer: str = Field(min_length=1, max_length=64_000)


def _scope(request: Request, project_id: str) -> RequestScope:
    # require_user rejects bearer tokens until a scope-aware M2 adapter exists.
    owner = require_user(request)
    try:
        return RequestScope(owner or '__local_operator__', project_id)
    except ValueError as exc:
        raise HTTPException(400, detail={'code': 'invalid_project', 'message': 'Invalid project ID'}) from exc


def _reply(operation: str, callback: Callable[[], dict[str, Any]], *, mutation: bool = False) -> dict[str, Any]:
    try:
        payload = callback()
    except (ValueError, VerifiedMemoryError, OSError, sqlite3.Error) as exc:
        status, code = 400, 'invalid_request'
        if isinstance(exc, RecordNotFoundError):
            status, code = 404, 'not_found'
        elif isinstance(exc, ContextNotReadyError):
            status, code = 409, 'context_not_ready'
        message = 'Project storage is unavailable' if isinstance(exc, (OSError, sqlite3.Error)) else str(exc)
        failure = VerifiedMemoryServiceEnvelope.failure(
            operation, {'code': code, 'message': message},
            audit={'operation': operation, 'mutation_performed': False, 'web_called': False, 'llm_called': False},
            metadata={'service_boundary': 'VerifiedMemoryService', 'contract_version': CONTRACT_VERSION},
        ).to_dict()
        raise HTTPException(status, detail=failure) from exc
    return VerifiedMemoryServiceEnvelope.success(
        operation, payload,
        audit={'operation': operation, 'mutation_performed': mutation, 'web_called': False, 'llm_called': False},
        metadata={'service_boundary': 'VerifiedMemoryService', 'contract_version': CONTRACT_VERSION},
    ).to_dict()


def setup_verified_memory_routes(workspace: VerifiedMemoryWorkspace | None = None) -> APIRouter:
    workspace = workspace or VerifiedMemoryWorkspace()
    router = APIRouter(prefix='/api/verified-memory', tags=['verified-memory'])

    @router.get('/health')
    async def health() -> dict[str, Any]:
        return {'ok': True, 'contract_version': CONTRACT_VERSION, 'capabilities': {
            'project_sources': True, 'query_evidence': True, 'prepare_task_context': True,
            'generate_answer': False, 'web_verification': False, 'path_import': False,
            'claim_support_verification': False, 'legacy_memory_mutation': False,
        }}

    @router.post('/projects')
    async def create_project(body: ProjectRequest, request: Request) -> dict[str, Any]:
        scope = _scope(request, body.project_id)
        def create() -> dict[str, Any]:
            workspace.create_project(scope)
            return {'project_id': scope.project_id}
        return _reply('create_project', create, mutation=True)

    @router.get('/projects/{project_id}/sources')
    async def list_sources(project_id: str, request: Request, include_history: bool = False, as_of: str | None = None) -> dict[str, Any]:
        scope = _scope(request, project_id)
        return _reply('list_sources', lambda: {'sources': [
            s.to_dict() for s in workspace.open_project(scope).list_sources(as_of=as_of, include_history=include_history)
        ]})

    @router.post('/projects/{project_id}/sources')
    async def import_source(project_id: str, body: SourceRequest, request: Request) -> dict[str, Any]:
        scope = _scope(request, project_id)
        return _reply('register_source', lambda: workspace.open_project(scope, write=True).register_source(
            SourceInput(**body.model_dump()),
        ).to_dict(), mutation=True)

    @router.get('/projects/{project_id}/sources/{revision_id}')
    async def inspect_source(project_id: str, revision_id: str, request: Request) -> dict[str, Any]:
        scope = _scope(request, project_id)
        return _reply('inspect_source', lambda: workspace.open_project(scope).inspect_source(revision_id).to_dict(include_text=True))

    @router.post('/projects/{project_id}/query')
    async def query(project_id: str, body: QueryRequest, request: Request) -> dict[str, Any]:
        scope = _scope(request, project_id)
        return _reply('query_evidence', lambda: workspace.open_project(scope).query_evidence(body.query()).to_dict())

    @router.post('/projects/{project_id}/prepare-context')
    async def prepare(project_id: str, body: PrepareRequest, request: Request) -> dict[str, Any]:
        scope = _scope(request, project_id)
        return _reply('prepare_task_context', lambda: workspace.open_project(scope).prepare_task_context(
            body.query(), max_age_seconds=body.max_age_seconds, expected_revisions=body.expected_revisions,
        ).to_dict())

    def service(request: Request, body: _ReadOnlyRequest) -> VerifiedMemoryService:
        return workspace.open_project(_scope(request, body.project_id))

    @router.post('/context')
    async def context(body: _ReadOnlyRequest, request: Request) -> dict[str, Any]:
        _scope(request, body.project_id)
        return _reply('build_context', lambda: service(request, body).build_context(
            body.question, max_chunks=body.max_chunks, max_claims=body.max_claims, include_archived=body.include_archived,
        ))

    @router.post('/prompt')
    async def prompt(body: _ReadOnlyRequest, request: Request) -> dict[str, Any]:
        _scope(request, body.project_id)
        return _reply('build_prompt', lambda: service(request, body).build_prompt(
            body.question, max_chunks=body.max_chunks, max_claims=body.max_claims, include_archived=body.include_archived,
        ))

    @router.post('/validate-answer')
    async def validate(body: VerifiedMemoryValidateAnswerRequest, request: Request) -> dict[str, Any]:
        _scope(request, body.project_id)
        return _reply('validate_answer', lambda: service(request, body).validate_answer(
            body.question, body.answer, max_chunks=body.max_chunks,
            max_claims=body.max_claims, include_archived=body.include_archived,
        ))

    @router.post('/admin/ingest')
    @router.post('/admin/extract-claims')
    async def retired_path_operation(request: Request) -> dict[str, Any]:
        require_user(request)
        require_admin(request)
        raise HTTPException(410, detail={
            'code': 'path_operations_retired',
            'message': 'Use scoped project source upload; server paths are no longer accepted.',
        })

    return router
