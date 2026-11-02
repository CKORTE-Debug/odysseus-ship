"""Application boundary for one supervised, local, source-backed model step.

This bounded in-process runner is not a multi-worker lease/DAG scheduler. A
process restart leaves checkpoints available for explicit human resumption.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from companion_core.checkpoints import SQLiteCheckpointStore
from companion_core.kernel import (
    CompanionKernel,
    LocalModelGateway,
    OdysseusLocalAdapter,
)
from verified_memory.contracts.project_contract import EvidenceQuery, RequestScope
from verified_memory.errors import RecordNotFoundError
from verified_memory.models._helpers import datetime_to_json, utc_now
from verified_memory.service import VerifiedMemoryWorkspace


class CompanionConflictError(ValueError):
    pass


class CompanionBusyError(CompanionConflictError):
    pass


class LocalModelRegistry(Protocol):
    def list_models(self, scope: RequestScope) -> list[dict[str, str]]: ...
    def resolve(self, scope: RequestScope, endpoint_id: str, model: str) -> OdysseusLocalAdapter: ...


@dataclass(frozen=True)
class ProjectTaskSpec:
    task_id: str
    query: EvidenceQuery
    endpoint_id: str
    model: str

    def payload(self) -> dict[str, Any]:
        return {'query': asdict(self.query), 'endpoint_id': self.endpoint_id, 'model': self.model}


class ProjectCompanionService:
    def __init__(self, memory: VerifiedMemoryWorkspace, registry: LocalModelRegistry, root: str | Path | None = None):
        if root is None:
            from src.constants import DATA_DIR
            root = os.getenv('COMPANION_DATA_DIR') or Path(DATA_DIR) / 'companion'
        self.root = Path(root).resolve()
        self.memory, self.registry = memory, registry
        self._handles: dict[tuple[str, str, str], asyncio.Task] = {}
        self._slot = asyncio.Semaphore(1)
        self._closed = False

    def _journal_path(self) -> Path:
        path = self.root / 'tasks.sqlite3'
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Linked checkpoint storage is not allowed')
        return path

    def _journal(self) -> SQLiteCheckpointStore:
        if not self._journal_path().is_file():
            raise CompanionConflictError('Enable local project steps before running a task')
        return SQLiteCheckpointStore(self._journal_path())

    @staticmethod
    def _key(scope: RequestScope, task_id: str) -> tuple[str, str, str]:
        return scope.actor_id, scope.project_id, task_id

    def initialize(self, scope: RequestScope) -> dict[str, Any]:
        self.memory.open_project(scope)
        SQLiteCheckpointStore.create(self._journal_path())
        return {'ready': True}

    def models(self, scope: RequestScope) -> list[dict[str, str]]:
        self.memory.open_project(scope)
        return self.registry.list_models(scope)

    def list_tasks(self, scope: RequestScope) -> dict[str, Any]:
        self.memory.open_project(scope)
        if not self._journal_path().is_file():
            return {'ready': False, 'tasks': []}
        tasks = self._journal().list_tasks(scope)
        for task in tasks:
            task.pop('answer', None)
            task.pop('validation', None)
            task['live'] = self._key(scope, task['task_id']) in self._handles
        return {'ready': True, 'tasks': tasks}

    def task(self, scope: RequestScope, task_id: str) -> dict[str, Any]:
        self.memory.open_project(scope)
        version, payload = self._journal().load(scope, task_id)
        if not version:
            raise RecordNotFoundError('Project task not found')
        return {**payload, 'task_id': task_id, 'checkpoint_version': version,
                'live': self._key(scope, task_id) in self._handles, 'claim_support': 'not_evaluated'}

    def _capacity(self):
        if self._closed:
            raise CompanionConflictError('Project runner is shutting down')
        if len(self._handles) >= 8:
            raise CompanionBusyError('Local project queue is full; wait or cancel another task')

    def start(self, scope: RequestScope, spec: ProjectTaskSpec) -> dict[str, Any]:
        journal = self._journal()
        version, previous = journal.load(scope, spec.task_id)
        if version:
            if previous.get('task_spec') != spec.payload():
                raise CompanionConflictError('Task ID already belongs to a different request')
            return self.task(scope, spec.task_id)
        self._capacity()
        self.registry.resolve(scope, spec.endpoint_id, spec.model)
        self.memory.open_project(scope).prepare_task_context(spec.query)
        payload = {'status': 'queued', 'attempt': 0, 'task_spec': spec.payload(),
                   'question': spec.query.question, 'queued_at': datetime_to_json(utc_now())}
        version = journal.save(scope, spec.task_id, payload, expected_version=0)
        self._schedule(scope, spec, version)
        return self.task(scope, spec.task_id)

    def _schedule(self, scope: RequestScope, spec: ProjectTaskSpec, version: int):
        key = self._key(scope, spec.task_id)
        if key in self._handles:
            raise CompanionConflictError('Task is already running')
        self._handles[key] = asyncio.create_task(self._execute(scope, spec, version))

    async def _execute(self, scope: RequestScope, spec: ProjectTaskSpec, version: int):
        key = self._key(scope, spec.task_id)
        try:
            async with self._slot:
                memory = self.memory.open_project(scope)
                adapter = self.registry.resolve(scope, spec.endpoint_id, spec.model)
                kernel = CompanionKernel(scope, memory, LocalModelGateway(memory, {spec.endpoint_id: adapter}), self._journal())
                await kernel.run(spec.task_id, spec.query, spec.endpoint_id, expected_version=version, resume=True)
        except (Exception, asyncio.CancelledError) as exc:  # noqa: BLE001 — background worker records provider failures
            # Kernel failures/cancellations already checkpoint themselves. This
            # covers cancellation while queued and failures before kernel entry.
            current, payload = self._journal().load(scope, spec.task_id)
            if payload.get('status') in {'queued', 'running'}:
                payload.update(status='paused' if isinstance(exc, asyncio.CancelledError) else 'failed', error_type=type(exc).__name__)
                self._journal().save(scope, spec.task_id, payload, expected_version=current)
        finally:
            self._handles.pop(key, None)

    def resume(self, scope: RequestScope, task_id: str, expected_version: int) -> dict[str, Any]:
        task = self.task(scope, task_id)
        if task['checkpoint_version'] != expected_version or task['live']:
            raise CompanionConflictError('Task changed or is still running; refresh it first')
        if task['status'] not in {'failed', 'paused', 'running', 'queued'}:
            raise CompanionConflictError('Only interrupted or failed tasks can resume')
        if task.get('attempt', 0) >= 2:
            raise CompanionConflictError('Attempt budget exhausted; create a reviewed follow-up task')
        data = task['task_spec']
        spec = ProjectTaskSpec(task_id, EvidenceQuery(**data['query']), data['endpoint_id'], data['model'])
        self._capacity()
        self.registry.resolve(scope, spec.endpoint_id, spec.model)
        self.memory.open_project(scope).prepare_task_context(spec.query)
        _, payload = self._journal().load(scope, task_id)
        payload.update(status='queued', resumed_at=datetime_to_json(utc_now()))
        payload.pop('error_type', None)
        version = self._journal().save(scope, task_id, payload, expected_version=expected_version)
        self._schedule(scope, spec, version)
        return self.task(scope, task_id)

    async def cancel(self, scope: RequestScope, task_id: str, expected_version: int) -> dict[str, Any]:
        task = self.task(scope, task_id)
        if task['checkpoint_version'] != expected_version:
            raise CompanionConflictError('Task changed; refresh it first')
        handle = self._handles.get(self._key(scope, task_id))
        if handle is not None:
            handle.cancel()
            await asyncio.gather(handle, return_exceptions=True)
            self._handles.pop(self._key(scope, task_id), None)
            current, payload = self._journal().load(scope, task_id)
            if payload.get('status') in {'queued', 'running'}:
                payload['status'] = 'paused'
                self._journal().save(scope, task_id, payload, expected_version=current)
        elif task['status'] in {'queued', 'running'}:
            _, payload = self._journal().load(scope, task_id)
            payload['status'] = 'paused'
            self._journal().save(scope, task_id, payload, expected_version=expected_version)
        else:
            raise CompanionConflictError('Task is not running')
        return self.task(scope, task_id)

    def review(self, scope: RequestScope, task_id: str, expected_version: int, decision: str) -> dict[str, Any]:
        task = self.task(scope, task_id)
        if task['checkpoint_version'] != expected_version or task['status'] != 'review_required' or task['live']:
            raise CompanionConflictError('Only the current completed output can be reviewed')
        if decision not in {'acknowledged', 'rejected'}:
            raise ValueError('Invalid review decision')
        _, payload = self._journal().load(scope, task_id)
        payload.update(status='reviewed' if decision == 'acknowledged' else 'rejected',
                       review={'decision': decision, 'reviewed_by': scope.actor_id, 'reviewed_at': datetime_to_json(utc_now())})
        self._journal().save(scope, task_id, payload, expected_version=expected_version)
        return self.task(scope, task_id)

    async def close(self):
        self._closed = True
        handles = list(self._handles.values())
        for handle in handles:
            handle.cancel()
        await asyncio.gather(*handles, return_exceptions=True)
        self._handles.clear()
