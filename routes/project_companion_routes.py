"""Browser-owned supervised project steps, using configured local models only."""

from __future__ import annotations

import inspect
import sqlite3
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from companion_core.application import (
    CompanionBusyError,
    CompanionConflictError,
    ProjectCompanionService,
    ProjectTaskSpec,
)
from companion_core.checkpoints import CheckpointConflictError
from src.project_scope import require_project_scope
from verified_memory.contracts.project_contract import EvidenceQuery
from verified_memory.errors import (
    ContextNotReadyError,
    RecordNotFoundError,
    VerifiedMemoryError,
)


class StartProjectTask(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    question: str = Field(min_length=1, max_length=4000)
    endpoint_id: str = Field(min_length=1, max_length=256)
    model: str = Field(min_length=1, max_length=256)
    context_budget_chars: int = Field(default=64_000, ge=256, le=64_000)


class TaskVersion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)


class ReviewProjectTask(TaskVersion):
    decision: Literal['acknowledged', 'rejected']


async def _result(callback):
    try:
        result = callback()
        if inspect.isawaitable(result):
            result = await result
        return {'ok': True, 'payload': result, 'contract_version': '1.0'}
    except (ValueError, VerifiedMemoryError, CheckpointConflictError, OSError, sqlite3.Error) as exc:
        status, code = 400, 'invalid_request'
        if isinstance(exc, RecordNotFoundError):
            status, code = 404, 'not_found'
        elif isinstance(exc, CompanionBusyError):
            status, code = 429, 'queue_full'
        elif isinstance(exc, (CompanionConflictError, CheckpointConflictError, ContextNotReadyError)):
            status, code = 409, 'task_not_ready'
        elif isinstance(exc, (OSError, sqlite3.Error)):
            status, code = 503, 'storage_unavailable'
        message = 'Local project storage is unavailable' if status == 503 else str(exc)
        raise HTTPException(status, detail={'code': code, 'message': message}) from exc


def setup_project_companion_routes(service: ProjectCompanionService) -> APIRouter:
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await service.close()

    router = APIRouter(prefix='/api/project-companion/projects/{project_id}', tags=['project-companion'], lifespan=lifespan)

    @router.post('/initialize')
    async def initialize(project_id: str, request: Request):
        scope = require_project_scope(request, project_id)
        return await _result(lambda: service.initialize(scope))

    @router.get('/models')
    async def models(project_id: str, request: Request):
        scope = require_project_scope(request, project_id)
        return await _result(lambda: {'models': service.models(scope)})

    @router.get('/tasks')
    async def tasks(project_id: str, request: Request):
        scope = require_project_scope(request, project_id)
        return await _result(lambda: service.list_tasks(scope))

    @router.post('/tasks', status_code=202)
    async def start(project_id: str, body: StartProjectTask, request: Request):
        scope = require_project_scope(request, project_id)
        spec = ProjectTaskSpec(body.task_id, EvidenceQuery(body.question, context_budget_chars=body.context_budget_chars), body.endpoint_id, body.model)
        return await _result(lambda: service.start(scope, spec))

    @router.get('/tasks/{task_id}')
    async def task(project_id: str, task_id: str, request: Request):
        scope = require_project_scope(request, project_id)
        return await _result(lambda: service.task(scope, task_id))

    @router.post('/tasks/{task_id}/resume', status_code=202)
    async def resume(project_id: str, task_id: str, body: TaskVersion, request: Request):
        scope = require_project_scope(request, project_id)
        return await _result(lambda: service.resume(scope, task_id, body.expected_version))

    @router.post('/tasks/{task_id}/cancel')
    async def cancel(project_id: str, task_id: str, body: TaskVersion, request: Request):
        scope = require_project_scope(request, project_id)
        return await _result(lambda: service.cancel(scope, task_id, body.expected_version))

    @router.post('/tasks/{task_id}/review')
    async def review(project_id: str, task_id: str, body: ReviewProjectTask, request: Request):
        scope = require_project_scope(request, project_id)
        return await _result(lambda: service.review(scope, task_id, body.expected_version, body.decision))

    return router
