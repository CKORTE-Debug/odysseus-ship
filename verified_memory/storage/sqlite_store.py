"""Standalone SQLite storage for verified-memory records."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from verified_memory.errors import InvalidRecordError, RecordNotFoundError
from verified_memory.models import ConflictRecord, DocumentChunk, MemoryClaim, VerificationRun
from verified_memory.models._helpers import parse_datetime, utc_now


class SQLiteVerifiedMemoryStore:
    """Small sqlite3-backed store for Milestone 1 verified-memory records."""

    def __init__(self, db_path: str | Path, *, initialize: bool = True, read_only: bool = False):
        self.db_path = str(db_path)
        self.read_only = read_only
        if read_only and not Path(self.db_path).is_file():
            raise RecordNotFoundError("Verified-memory project has not been initialized")
        if initialize and not read_only:
            self.initialize()

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_claims (
                    id TEXT PRIMARY KEY,
                    claim TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE(document_id, chunk_id)
                );

                CREATE TABLE IF NOT EXISTS conflict_records (
                    id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    conflicting_claim_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS verification_runs (
                    id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS project_identity (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    actor_id TEXT NOT NULL,
                    project_id TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS source_revisions (
                    revision_id TEXT PRIMARY KEY,
                    source_key TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_source_revisions_key_time
                    ON source_revisions(source_key, effective_from, imported_at);

                CREATE TABLE IF NOT EXISTS source_observations (
                    revision_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY(revision_id, observed_at)
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS ix_conflicts_claim_id ON conflict_records(claim_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_verification_runs_claim_id ON verification_runs(claim_id)")

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            conn = sqlite3.connect(Path(self.db_path).absolute().as_uri() + "?mode=ro", uri=True)
        else:
            conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def bind_project(self, actor_id: str, project_id: str) -> None:
        """Bind an application-owned database once; never reassign ownership."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO project_identity VALUES (1, ?, ?)", (actor_id, project_id)
            )
            row = conn.execute("SELECT actor_id, project_id FROM project_identity WHERE singleton=1").fetchone()
            if (row["actor_id"], row["project_id"]) != (actor_id, project_id):
                raise InvalidRecordError("Project identity mismatch")

    def check_project(self, actor_id: str, project_id: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT actor_id, project_id FROM project_identity WHERE singleton=1").fetchone()
        if row is None or (row["actor_id"], row["project_id"]) != (actor_id, project_id):
            raise InvalidRecordError("Project identity mismatch")

    def register_source_revision(
        self, payload: dict[str, Any], chunks: list[DocumentChunk], *, deduplicate_latest: bool = False,
    ) -> dict[str, Any]:
        """Atomically enforce revision identity, deduplication and provenance."""
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            previous = [json.loads(row[0]) for row in conn.execute(
                'SELECT payload FROM source_revisions WHERE source_key=?', (payload['source_key'],)
            ).fetchall()]
            if any(p['authority'] == 'canonical' for p in previous) and payload['authority'] != 'canonical':
                raise InvalidRecordError('An approved canonical source cannot be replaced by an ordinary upload')
            if payload.get('external_revision') and any(
                p.get('external_revision') == payload['external_revision'] and p['content_sha256'] != payload['content_sha256']
                for p in previous
            ):
                raise InvalidRecordError('An external revision cannot identify different source content')
            # Check at commit time: concurrent requests can acquire the lock in
            # a different order from their initial import timestamps.
            commit_time = utc_now()
            eligible = [p for p in previous if parse_datetime(p['effective_from'], 'effective_from') <= commit_time]
            latest = max(eligible, key=lambda p: (
                parse_datetime(p['effective_from'], 'effective_from'), parse_datetime(p['imported_at'], 'imported_at'), p['revision_id'],
            ), default=None)
            descriptor_keys = (
                'source_key', 'filename', 'content_sha256', 'authority', 'canonical_role',
                'owner_approved', 'sensitivity', 'source_url', 'external_revision',
            )
            if deduplicate_latest and latest and all(latest[k] == payload[k] for k in descriptor_keys):
                conn.execute('INSERT OR IGNORE INTO source_observations VALUES (?, ?)',
                             (latest['revision_id'], payload['imported_at']))
                return latest
            existing = conn.execute(
                "SELECT payload FROM source_revisions WHERE revision_id=?", (payload["revision_id"],)
            ).fetchone()
            if existing:
                conn.execute('INSERT OR IGNORE INTO source_observations VALUES (?, ?)',
                             (payload['revision_id'], payload['imported_at']))
                return json.loads(existing['payload'])
            conn.execute(
                "INSERT INTO source_revisions VALUES (?, ?, ?, ?, ?)",
                (payload["revision_id"], payload["source_key"], payload["effective_from"],
                 payload["imported_at"], json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )
            for chunk in chunks:
                conn.execute(
                    "INSERT INTO document_chunks (id, document_id, chunk_id, payload) VALUES (?, ?, ?, ?)",
                    (chunk.id, chunk.document_id, chunk.chunk_id, self._dump(chunk)),
                )
            conn.execute('INSERT OR IGNORE INTO source_observations VALUES (?, ?)',
                         (payload['revision_id'], payload['imported_at']))
            return payload

    def record_source_observation(self, revision_id: str, observed_at: str) -> None:
        with self._connect() as conn:
            if conn.execute('SELECT 1 FROM source_revisions WHERE revision_id=?', (revision_id,)).fetchone() is None:
                raise RecordNotFoundError('Source revision not found')
            conn.execute('INSERT OR IGNORE INTO source_observations VALUES (?, ?)', (revision_id, observed_at))

    def source_last_observed_at(self, revision_id: str) -> str | None:
        with self._connect() as conn:
            rows = conn.execute('SELECT observed_at FROM source_observations WHERE revision_id=?', (revision_id,)).fetchall()
        return max((row[0] for row in rows), key=lambda value: parse_datetime(value, 'observed_at'), default=None)

    def list_source_revisions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM source_revisions ORDER BY source_key, effective_from, imported_at, revision_id"
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_source_revision(self, revision_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM source_revisions WHERE revision_id=?", (revision_id,)).fetchone()
        if row is None:
            raise RecordNotFoundError("Source revision not found")
        return json.loads(row["payload"])

    @staticmethod
    def _dump(record: Any) -> str:
        try:
            return json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True)
        except (TypeError, AttributeError) as exc:
            raise InvalidRecordError(f"record is not JSON serializable: {record!r}") from exc

    @staticmethod
    def _load_payload(row: sqlite3.Row | None, model_cls: type) -> Any:
        if row is None:
            return None
        try:
            payload = json.loads(row["payload"])
            return model_cls.from_dict(payload)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            raise InvalidRecordError(f"stored {model_cls.__name__} payload is invalid") from exc

    def add_memory_claim(self, claim: MemoryClaim) -> MemoryClaim:
        payload = self._dump(claim)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memory_claims (id, claim, status, payload) VALUES (?, ?, ?, ?)",
                (claim.id, claim.claim, claim.status, payload),
            )
        return claim

    def get_memory_claim(self, claim_id: str) -> MemoryClaim:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM memory_claims WHERE id = ?", (claim_id,)).fetchone()
        record = self._load_payload(row, MemoryClaim)
        if record is None:
            raise RecordNotFoundError(f"MemoryClaim not found: {claim_id}")
        return record

    def update_memory_claim(self, claim: MemoryClaim) -> MemoryClaim:
        payload = self._dump(claim)
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE memory_claims SET claim = ?, status = ?, payload = ? WHERE id = ?",
                (claim.claim, claim.status, payload, claim.id),
            )
            if result.rowcount == 0:
                raise RecordNotFoundError(f"MemoryClaim not found: {claim.id}")
        return claim

    def list_memory_claims(self, *, include_archived: bool = True) -> list[MemoryClaim]:
        query = "SELECT payload FROM memory_claims"
        params: tuple[Any, ...] = ()
        if not include_archived:
            query += " WHERE status != ?"
            params = ("archived",)
        query += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._load_payload(row, MemoryClaim) for row in rows]

    def list_memory_claims_by_source_chunk(self, chunk_id: str) -> list[MemoryClaim]:
        return [
            claim
            for claim in self.list_memory_claims()
            if any(ref.chunk_id == chunk_id for ref in claim.source_refs)
        ]

    def list_memory_claims_by_document_id(self, document_id: str) -> list[MemoryClaim]:
        return [
            claim
            for claim in self.list_memory_claims()
            if any(ref.source_id == document_id for ref in claim.source_refs)
        ]

    def archive_memory_claim(self, claim_id: str) -> MemoryClaim:
        claim = self.get_memory_claim(claim_id)
        claim.status = "archived"
        claim.__post_init__()
        return self.update_memory_claim(claim)

    def delete_memory_claim(self, claim_id: str) -> None:
        with self._connect() as conn:
            result = conn.execute("DELETE FROM memory_claims WHERE id = ?", (claim_id,))
            if result.rowcount == 0:
                raise RecordNotFoundError(f"MemoryClaim not found: {claim_id}")

    def add_document_chunk(self, chunk: DocumentChunk) -> DocumentChunk:
        payload = self._dump(chunk)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO document_chunks (id, document_id, chunk_id, payload)
                VALUES (?, ?, ?, ?)
                """,
                (chunk.id, chunk.document_id, chunk.chunk_id, payload),
            )
        return chunk

    def get_document_chunk(self, chunk_id: str) -> DocumentChunk:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM document_chunks WHERE id = ? OR chunk_id = ?",
                (chunk_id, chunk_id),
            ).fetchone()
        record = self._load_payload(row, DocumentChunk)
        if record is None:
            raise RecordNotFoundError(f"DocumentChunk not found: {chunk_id}")
        return record

    def list_document_chunks(self, document_id: str | None = None) -> list[DocumentChunk]:
        query = "SELECT payload FROM document_chunks"
        params: tuple[Any, ...] = ()
        if document_id is not None:
            query += " WHERE document_id = ?"
            params = (document_id,)
        query += " ORDER BY document_id, chunk_id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._load_payload(row, DocumentChunk) for row in rows]

    def list_document_chunks_by_document_id(self, document_id: str) -> list[DocumentChunk]:
        return self.list_document_chunks(document_id=document_id)

    def delete_document_chunks_by_document_id(self, document_id: str) -> int:
        with self._connect() as conn:
            result = conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
            return int(result.rowcount or 0)

    def count_documents(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(DISTINCT document_id) AS count FROM document_chunks").fetchone()
        return int(row["count"] or 0)

    def count_document_chunks(self) -> int:
        return self._count_table("document_chunks")

    def count_memory_claims(self) -> int:
        return self._count_table("memory_claims")

    def count_conflict_records(self) -> int:
        return self._count_table("conflict_records")

    def count_verification_runs(self) -> int:
        return self._count_table("verification_runs")

    def _count_table(self, table_name: str) -> int:
        allowed_tables = {
            "document_chunks",
            "memory_claims",
            "conflict_records",
            "verification_runs",
        }
        if table_name not in allowed_tables:
            raise InvalidRecordError(f"unsupported count table: {table_name}")
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"] or 0)

    def search_document_chunks_basic(self, query: str, *, limit: int = 20) -> list[DocumentChunk]:
        if not str(query or "").strip():
            raise InvalidRecordError("query must not be empty")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM document_chunks WHERE payload LIKE ? ORDER BY document_id, chunk_id LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [self._load_payload(row, DocumentChunk) for row in rows]

    def add_conflict_record(self, conflict: ConflictRecord) -> ConflictRecord:
        payload = self._dump(conflict)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conflict_records
                    (id, claim_id, conflicting_claim_id, status, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conflict.id, conflict.claim_id, conflict.conflicting_claim_id, conflict.status, payload),
            )
        return conflict

    def get_conflict_record(self, conflict_id: str) -> ConflictRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM conflict_records WHERE id = ?", (conflict_id,)).fetchone()
        record = self._load_payload(row, ConflictRecord)
        if record is None:
            raise RecordNotFoundError(f"ConflictRecord not found: {conflict_id}")
        return record

    def list_conflicts_for_claim(self, claim_id: str) -> list[ConflictRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM conflict_records
                WHERE claim_id = ? OR conflicting_claim_id = ?
                ORDER BY id
                """,
                (claim_id, claim_id),
            ).fetchall()
        return [self._load_payload(row, ConflictRecord) for row in rows]

    def add_verification_run(self, run: VerificationRun) -> VerificationRun:
        payload = self._dump(run)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO verification_runs (id, claim_id, status, payload) VALUES (?, ?, ?, ?)",
                (run.id, run.claim_id, run.status, payload),
            )
        return run

    def get_verification_run(self, run_id: str) -> VerificationRun:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM verification_runs WHERE id = ?", (run_id,)).fetchone()
        record = self._load_payload(row, VerificationRun)
        if record is None:
            raise RecordNotFoundError(f"VerificationRun not found: {run_id}")
        return record

    def list_verification_runs_for_claim(self, claim_id: str) -> list[VerificationRun]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM verification_runs WHERE claim_id = ? ORDER BY id",
                (claim_id,),
            ).fetchall()
        return [self._load_payload(row, VerificationRun) for row in rows]
