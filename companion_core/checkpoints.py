"""Small durable checkpoint journal, separate from factual memory.

Versions prevent simultaneous writers overwriting each other. This is not a
lease scheduler or an exactly-once tool execution engine.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from verified_memory.contracts.project_contract import RequestScope


class CheckpointConflictError(RuntimeError):
    pass


class SQLiteCheckpointStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError('Initialize the checkpoint journal explicitly')

    @classmethod
    def create(cls, path: str | Path) -> SQLiteCheckpointStore:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS task_checkpoints (
                scope TEXT NOT NULL, task_id TEXT NOT NULL,
                version INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(scope, task_id)
            )''')
        return cls(path)

    @staticmethod
    def _scope(scope: RequestScope, task_id: str) -> str:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', task_id):
            raise ValueError('Invalid task ID')
        return hashlib.sha256(json.dumps([scope.actor_id, scope.project_id]).encode()).hexdigest()

    def load(self, scope: RequestScope, task_id: str) -> tuple[int, dict[str, Any]]:
        key = self._scope(scope, task_id)
        with sqlite3.connect(self.path.absolute().as_uri() + '?mode=ro', uri=True) as conn:
            row = conn.execute(
                'SELECT version, payload FROM task_checkpoints WHERE scope=? AND task_id=?', (key, task_id),
            ).fetchone()
        return (row[0], json.loads(row[1])) if row else (0, {})

    def save(self, scope: RequestScope, task_id: str, payload: dict[str, Any], *, expected_version: int) -> int:
        key = self._scope(scope, task_id)
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > 256_000:
            raise ValueError('Checkpoint exceeds its size budget')
        # mode=rw refuses to recreate a deleted journal during a write.
        with sqlite3.connect(self.path.absolute().as_uri() + '?mode=rw', uri=True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                'SELECT version FROM task_checkpoints WHERE scope=? AND task_id=?', (key, task_id),
            ).fetchone()
            if (row[0] if row else 0) != expected_version:
                raise CheckpointConflictError('Checkpoint changed; reload before resuming')
            version = expected_version + 1
            conn.execute('INSERT OR REPLACE INTO task_checkpoints VALUES (?, ?, ?, ?)', (key, task_id, version, encoded))
        return version
