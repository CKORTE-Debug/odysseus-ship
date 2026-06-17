# 05 - Architecture and Data Model

## Architecture principle
Verified Memory should begin as a standalone backend module. It should not modify Odysseus legacy memory, search, ChromaDB, or UI routes until deterministic storage and policy behavior are covered by tests.

## Recommended initial package structure

```text
verified_memory/
  __init__.py
  models/
    __init__.py
    memory_claim.py
    source_ref.py
    document_chunk.py
    conflict_record.py
    verification_run.py
    domain_profile.py
    policy_decision.py
  storage/
    __init__.py
    sqlite_store.py
    migrations.sql
  verification/
    __init__.py
    staleness.py
    query_sanitizer.py
    source_ranker.py
    evidence_checker.py
    conflict_detector.py
  ingestion/
    __init__.py
    document_loader.py
    chunker.py
    claim_extractor.py
  retrieval/
    __init__.py
    keyword_search.py
    memory_retriever.py
  workflows/
    __init__.py
    ingest_document.py
    ask_with_verified_memory.py
    refresh_memory.py
    audit_memory.py
  policies/
    source_policy.md
    privacy_policy.md
    staleness_policy.md
  cli.py
```

A flatter module is acceptable for Phase 1, but Codex should avoid mixing models, storage, policies, and workflows into one large file.

## Integration boundaries

### Legacy Odysseus memory
Existing simple memory in `src/memory.py` should remain untouched during early phases.

### Odysseus search
Existing search should only be called by Verified Memory after the deterministic query sanitizer approves the query.

### Odysseus LLM calls
When LLM integration begins, use `src.llm_core.llm_call_async` or existing streaming/fallback abstractions. Do not create a separate model HTTP client.

### ChromaDB/vector memory
Delay vector integration until `SourceRef` and `DocumentChunk` are stable. Semantic retrieval without evidence preservation must not become the source of truth.

## Core data objects

### MemoryClaim
A single reusable claim that may be used in future answers.

Required fields:

```json
{
  "id": "mem_001",
  "claim": "Windows 11 OOBE may require network connectivity depending on edition and setup path.",
  "claim_type": "software_behavior",
  "source_refs": [],
  "created_at": "2026-06-17T00:00:00Z",
  "last_verified_at": null,
  "stale_after_days": 60,
  "status": "unverified",
  "confidence": "low",
  "sensitivity": "public",
  "verification_policy": "official_vendor_first",
  "allowed_web_search": true,
  "domain": "it_software",
  "superseded_by": null,
  "conflicts_with": []
}
```

Allowed `status` values:

- `unverified`
- `verified`
- `stale`
- `contradicted`
- `archived`
- `candidate_update`

Allowed `confidence` values:

- `low`
- `medium`
- `high`

Allowed `sensitivity` values:

- `public`
- `private`
- `client_confidential`
- `personal_sensitive`

### SourceRef
A pointer from a claim to exact evidence.

Fields:

```json
{
  "source_id": "doc_surface_sop",
  "source_type": "local_document",
  "document_name": "Surface_Reinstall_SOP.md",
  "path": "docs/Surface_Reinstall_SOP.md",
  "page": null,
  "line_start": 20,
  "line_end": 34,
  "chunk_id": "doc_surface_sop:chunk:004",
  "quote": "If Wi-Fi drivers are missing during OOBE, load drivers from USB.",
  "url": null,
  "retrieved_at": null,
  "source_rank": null
}
```

Rules:

- Claims should cite `SourceRef` objects, not only file names.
- Local source chunks must preserve line or page references where available.
- Summaries are allowed but must not replace original quoted/source chunks.

### DocumentChunk
A chunk of original source material.

Fields:

```json
{
  "document_id": "doc_001",
  "document_name": "example.md",
  "path": "docs/example.md",
  "chunk_id": "doc_001:chunk:001",
  "text": "...",
  "line_start": 1,
  "line_end": 40,
  "created_at": "2026-06-17T00:00:00Z",
  "content_hash": "..."
}
```

### VerificationRun
An auditable record of an attempt to verify a memory.

Fields:

```json
{
  "id": "ver_001",
  "memory_claim_id": "mem_001",
  "started_at": "2026-06-17T00:00:00Z",
  "completed_at": null,
  "verification_type": "manual_web",
  "query_original": "...",
  "query_sanitized": "...",
  "query_status": "allowed",
  "sources_checked": [],
  "result": "pending",
  "notes": ""
}
```

Allowed query statuses:

- `allowed`
- `sanitized`
- `blocked`

Allowed results:

- `verified`
- `not_verified`
- `contradicted`
- `insufficient_evidence`
- `blocked_by_privacy`
- `error`

### ConflictRecord
A record of disagreement between claims or sources.

Fields:

```json
{
  "id": "conflict_001",
  "claim_ids": ["mem_001", "mem_002"],
  "description": "Older SOP conflicts with newer vendor documentation.",
  "created_at": "2026-06-17T00:00:00Z",
  "severity": "medium",
  "status": "open",
  "resolution": null
}
```

Allowed severity:

- `low`
- `medium`
- `high`

Allowed status:

- `open`
- `resolved`
- `ignored`

### DomainProfile
A domain-specific policy bundle.

Fields:

```json
{
  "name": "it_software",
  "default_stale_after_days": 60,
  "source_priority": ["official_vendor", "official_release_notes", "official_github"],
  "web_search_allowed": true,
  "manual_approval_required": false,
  "never_final_sources": ["forum_or_reddit"]
}
```

### PolicyDecision
A deterministic decision from a policy module.

Fields:

```json
{
  "allowed": true,
  "decision": "sanitized",
  "reason": "Removed denylisted client name.",
  "original_value": "...",
  "safe_value": "...",
  "warnings": []
}
```

## Storage guidance
Use standalone SQLite in Phase 1. Do not add tables to `core/database.py` until the module is stable.

Minimum tables:

- `memory_claims`
- `source_refs`
- `document_chunks`
- `verification_runs`
- `conflict_records`

JSON fields may be used initially for arrays, but source refs should become queryable when possible.

## Error handling rules
- Invalid enum values must raise validation errors.
- Failed storage writes must not partially save claims without source references.
- A failed verification run must be recorded as `error` or `blocked_by_privacy`.
- If source refs are missing, the claim must be `unverified` unless explicitly marked as user-provided.

## Coding guidance for Codex
- Keep models small and typed.
- Keep storage and policy logic deterministic.
- Do not add web or LLM calls in model/storage phases.
- Add pytest tests for every new model and storage behavior.
