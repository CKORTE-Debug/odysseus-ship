"""Scoped source revisions and deterministic context preflight; no network."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import PurePath
from urllib.parse import urlparse

from verified_memory.contracts.project_contract import (
    CONTRACT_VERSION,
    MAX_SOURCE_BYTES,
    EvidenceBundle,
    EvidencePassage,
    EvidenceQuery,
    PreparedTaskContext,
    RequestScope,
    SourceInput,
    SourceRevision,
)
from verified_memory.errors import ContextNotReadyError, InvalidRecordError
from verified_memory.ingestion import chunk_document
from verified_memory.ingestion.document_loader import LoadedDocument
from verified_memory.models._helpers import datetime_to_json, parse_datetime, utc_now
from verified_memory.retrieval import retrieve_chunks_by_keyword
from verified_memory.storage import SQLiteVerifiedMemoryStore


def _time(value: str | datetime | None, name: str) -> datetime:
    return parse_datetime(value, name) if value is not None else utc_now()


def register_source(store: SQLiteVerifiedMemoryStore, source: SourceInput) -> SourceRevision:
    name = source.filename
    key = source.source_key or name
    if not name or len(name) > 256 or any(c in name for c in '/\\:\x00') or name in {'.', '..'}:
        raise InvalidRecordError("Upload a filename, not a filesystem path")
    if PurePath(name).suffix.lower() not in {'.md', '.txt'}:
        raise InvalidRecordError("Only .md and .txt sources are supported")
    if not key.strip() or len(key) > 256 or any(ord(c) < 32 for c in key + name):
        raise InvalidRecordError("Invalid source key or filename")
    if not source.text.strip() or '\x00' in source.text:
        raise InvalidRecordError("Source must contain nonempty UTF-8 text")
    if len(source.text.encode('utf-8')) > MAX_SOURCE_BYTES:
        raise InvalidRecordError("Source exceeds the 2 MiB limit")
    if source.authority not in {'canonical', 'reference', 'working'}:
        raise InvalidRecordError("Invalid source authority")
    if source.sensitivity not in {'private', 'public'}:
        raise InvalidRecordError("Invalid sensitivity")
    if source.canonical_role not in {None, 'procedure', 'current_state', 'decision'}:
        raise InvalidRecordError("Invalid canonical role")
    if source.authority == 'canonical' and not source.owner_approved:
        raise InvalidRecordError("Canonical import requires explicit owner approval")
    if source.canonical_role and source.authority != 'canonical':
        raise InvalidRecordError("Only canonical sources can have a canonical role")
    if source.source_url:
        parsed = urlparse(source.source_url)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
            raise InvalidRecordError("Source URL must be an HTTPS reference without credentials")
        if len(source.source_url) > 2048:
            raise InvalidRecordError("Source URL is too long")
    if source.external_revision is not None and (not source.external_revision.strip() or len(source.external_revision) > 256):
        raise InvalidRecordError("Invalid external revision")

    now = utc_now()
    digest = hashlib.sha256(source.text.encode('utf-8')).hexdigest()
    descriptor = {
        'source_key': key, 'filename': name, 'content_sha256': digest,
        'authority': source.authority, 'canonical_role': source.canonical_role,
        'owner_approved': source.owner_approved, 'sensitivity': source.sensitivity,
        'source_url': source.source_url, 'external_revision': source.external_revision,
    }
    # Deduplication of the latest active revision is atomic in the store.
    # Re-uploading an older version intentionally creates a new revision.
    effective = datetime_to_json(_time(source.effective_from, 'effective_from'))
    revision_id = hashlib.sha256(json.dumps(
        {**descriptor, 'effective_from': effective}, sort_keys=True, ensure_ascii=False,
    ).encode('utf-8')).hexdigest()
    revision = SourceRevision(
        revision_id=revision_id, imported_at=datetime_to_json(now), effective_from=effective,
        text=source.text, **descriptor,
    )
    loaded = LoadedDocument(
        document_id=revision_id, document_name=name,
        document_path=f'source:{revision_id}', text=source.text,
        line_count=len(source.text.splitlines()), metadata={'content_sha256': digest},
    )
    chunks = chunk_document(loaded)
    stored = store.register_source_revision(asdict(revision), chunks, deduplicate_latest=source.effective_from is None)
    return SourceRevision(**stored)


def active_sources(store: SQLiteVerifiedMemoryStore, *, as_of: str | None = None) -> list[SourceRevision]:
    when = _time(as_of, 'as_of')
    selected: dict[str, SourceRevision] = {}
    for payload in store.list_source_revisions():
        source = SourceRevision(**payload)
        if _time(source.effective_from, 'effective_from') <= when:
            old = selected.get(source.source_key)
            if old is None or (
                _time(source.effective_from, 'effective_from'), _time(source.imported_at, 'imported_at'), source.revision_id,
            ) > (
                _time(old.effective_from, 'effective_from'), _time(old.imported_at, 'imported_at'), old.revision_id,
            ):
                selected[source.source_key] = source
    return list(selected.values())


def source_fingerprint(sources: list[SourceRevision]) -> str:
    return hashlib.sha256('\n'.join(sorted(s.revision_id for s in sources)).encode()).hexdigest()


def query_evidence(store: SQLiteVerifiedMemoryStore, scope: RequestScope, query: EvidenceQuery) -> EvidenceBundle:
    sources = {s.revision_id: s for s in active_sources(store, as_of=query.as_of)}
    chunks = [chunk for source_id in sources for chunk in store.list_document_chunks(source_id)]
    # Existing lexical retrieval remains the explicit baseline. Only active
    # revisions enter the ranker; an old lexical match cannot outrank its update.
    results = retrieve_chunks_by_keyword(query.question, chunks, max_results=max(query.limit, len(chunks)))
    passages: list[EvidencePassage] = []
    warnings = ['claim_support_not_evaluated', 'live_upstream_freshness_not_checked']
    used = 0
    for result in results:
        chunk = result.chunk
        source = sources[chunk.document_id]
        if hashlib.sha256(source.text.encode('utf-8')).hexdigest() != source.content_sha256:
            raise InvalidRecordError("Source integrity check failed")
        exact_text = '\n'.join(source.text.splitlines()[chunk.line_start - 1:chunk.line_end])
        if used + len(exact_text) > query.context_budget_chars:
            if 'passage_omitted_for_budget' not in warnings:
                warnings.append('passage_omitted_for_budget')
            continue
        passages.append(EvidencePassage(
            citation_ref=chunk.chunk_id, source=source, text=exact_text,
            line_start=chunk.line_start, line_end=chunk.line_end, score=result.score,
        ))
        used += len(exact_text)
        if len(passages) == query.limit:
            break
    if not passages:
        warnings.append('insufficient_matching_evidence')
    return EvidenceBundle(scope, query, tuple(passages), tuple(warnings))


def prepare_task_context(
    store: SQLiteVerifiedMemoryStore, scope: RequestScope, query: EvidenceQuery,
    *, max_age_seconds: int = 86_400, expected_revisions: dict[str, str] | None = None,
) -> PreparedTaskContext:
    if not 1 <= max_age_seconds <= 2_592_000:
        raise InvalidRecordError("Freshness window must be between 1 second and 30 days")
    if query.as_of is not None:
        raise ContextNotReadyError("Task preflight requires current evidence; historical queries are for inspection")
    now = utc_now()
    sources = active_sources(store)
    by_key = {s.source_key: s for s in sources}
    for key, expected in (expected_revisions or {}).items():
        source = by_key.get(key)
        if source is None or expected not in {source.revision_id, source.external_revision}:
            raise ContextNotReadyError(f"Source revision changed or is missing: {key}")
    required = [s for s in sources if s.canonical_role in {'procedure', 'current_state'}]
    if {s.canonical_role for s in required} != {'procedure', 'current_state'}:
        raise ContextNotReadyError("Approved procedure and current-state sources are required")
    for source in required:
        if source.authority != 'canonical' or not source.owner_approved:
            raise ContextNotReadyError("Required project context is not owner-approved")
        checked_at = store.source_last_observed_at(source.revision_id) or source.imported_at
        if now - _time(checked_at, 'checked_at') > timedelta(seconds=max_age_seconds):
            raise ContextNotReadyError(f"Refresh the imported project source: {source.source_key}")
        if hashlib.sha256(source.text.encode('utf-8')).hexdigest() != source.content_sha256:
            raise ContextNotReadyError("Required source integrity check failed")
    used = sum(len(s.text) for s in required)
    if used > query.context_budget_chars:
        raise ContextNotReadyError("Required project context exceeds the character budget; increase it or curate the records")
    evidence = query_evidence(store, scope, query)
    optional: list[EvidencePassage] = []
    warnings = list(evidence.warnings)
    for passage in evidence.passages:
        if passage.source in required:
            continue
        if used + len(passage.text) <= query.context_budget_chars:
            optional.append(passage)
            used += len(passage.text)
        elif 'optional_context_omitted_for_budget' not in warnings:
            warnings.append('optional_context_omitted_for_budget')
    evidence = EvidenceBundle(scope, query, tuple(optional), tuple(warnings))
    return PreparedTaskContext(
        scope, datetime_to_json(now), tuple(required), evidence, max_age_seconds, source_fingerprint(sources),
    )


def assert_context_current(store: SQLiteVerifiedMemoryStore, scope: RequestScope, context: PreparedTaskContext) -> None:
    if context.contract_version != CONTRACT_VERSION:
        raise ContextNotReadyError('Unsupported context contract version')
    if context.scope != scope:
        raise ContextNotReadyError("Prepared context belongs to a different actor/project")
    fresh = prepare_task_context(store, scope, context.evidence.query, max_age_seconds=context.max_age_seconds)
    if fresh.project_fingerprint != context.project_fingerprint:
        raise ContextNotReadyError("Project sources changed; prepare context again")
    if fresh.required_sources != context.required_sources or fresh.evidence != context.evidence:
        raise ContextNotReadyError("Prepared source content was altered; prepare context again")
    if utc_now() - _time(context.generated_at, 'generated_at') > timedelta(seconds=context.max_age_seconds):
        raise ContextNotReadyError("Prepared context expired; prepare context again")
