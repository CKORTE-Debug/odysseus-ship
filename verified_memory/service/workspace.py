"""Composition root: authenticated identity resolves to application-owned stores."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from verified_memory.contracts.project_contract import RequestScope
from verified_memory.errors import InvalidRecordError, RecordNotFoundError
from verified_memory.service.verified_memory_service import VerifiedMemoryService
from verified_memory.storage import SQLiteVerifiedMemoryStore


class VerifiedMemoryWorkspace:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv('VERIFIED_MEMORY_DATA_DIR', 'data/verified_memory')).resolve()

    @staticmethod
    def _key(value: str) -> str:
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    def _database_path(self, scope: RequestScope) -> Path:
        path = self.root / self._key(scope.actor_id) / self._key(scope.project_id) / 'memory.sqlite3'
        # Names come only from server hashes. Reject existing links/junctions
        # as well, rather than relying on a textual '..' check.
        for part in (path.parent.parent, path.parent, path):
            if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
                raise InvalidRecordError('Linked project storage is not allowed')
        if not path.resolve().is_relative_to(self.root):
            raise InvalidRecordError('Project storage escaped its configured root')
        return path

    def create_project(self, scope: RequestScope) -> VerifiedMemoryService:
        path = self._database_path(scope)
        if path.exists():
            return self.open_project(scope, write=True)
        store = SQLiteVerifiedMemoryStore(path)
        store.bind_project(scope.actor_id, scope.project_id)
        return VerifiedMemoryService(store, scope=scope)

    def open_project(self, scope: RequestScope, *, write: bool = False) -> VerifiedMemoryService:
        path = self._database_path(scope)
        if not path.is_file():
            raise RecordNotFoundError('Project not found; create it before importing sources')
        store = SQLiteVerifiedMemoryStore(path, initialize=False, read_only=not write)
        store.check_project(scope.actor_id, scope.project_id)
        return VerifiedMemoryService(store, scope=scope)
