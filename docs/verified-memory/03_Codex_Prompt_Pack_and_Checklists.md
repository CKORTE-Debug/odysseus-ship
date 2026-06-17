# Codex Prompt Pack and Phase Checklists

Use one phase prompt at a time. Inspect the diff, run tests, and commit before moving on.

## Phase 0 - Inspect Repository
```text
Inspect the Odysseus codebase.

I want to add a module called verified_memory that stores source-linked, timestamped, refreshable memory claims.

Do not modify files yet.

Please identify:
1. The main app framework and backend language/framework.
2. Existing memory implementation.
3. Existing vector DB/ChromaDB/fastembed integration.
4. Existing web/research/search integration.
5. Existing model call abstraction.
6. Existing test framework.
7. Where a standalone verified_memory module should live.
8. Any project conventions I should follow.
9. A minimal implementation plan for adding verified_memory without breaking existing behavior.
```

## Phase 1 - Data Models and SQLite Store
```text
Implement Phase 1 only: standalone verified_memory data models and SQLite storage.

Requirements:
- Do not integrate with UI.
- Do not call LLM.
- Do not call network.
- Add tests.
- Keep changes minimal.

Models:
- MemoryClaim
- SourceRef
- ConflictRecord

Fields for MemoryClaim:
- id
- claim
- claim_type
- source_refs
- created_at
- last_verified_at
- stale_after_days
- status
- confidence
- sensitivity
- verification_policy
- allowed_web_search
- superseded_by
- conflicts_with

Allowed status values: unverified, verified, stale, contradicted, archived.
Allowed confidence: low, medium, high.
Allowed sensitivity: public, private, client_confidential, personal_sensitive.

Storage:
- SQLite store with create/get/update/list operations.
- Round-trip tests.
```

## Phase 2 - Staleness Engine
```text
Implement verified_memory/verification/staleness.py.

It must determine whether a memory claim is fresh, stale, never_stale, unverified, or invalid. Use last_verified_at and stale_after_days. stale_after_days = null means never stale. Missing last_verified_at means unverified. Future last_verified_at means invalid. Include unit tests.

Do not use an LLM. Do not use web search.
```

## Phase 3 - Privacy-Safe Query Sanitizer
```text
Implement verified_memory/verification/query_sanitizer.py.

Before any online search, sanitize or block search queries to prevent leaking private data. Block emails, IPs, internal domains, ticket IDs, internal file paths, and client/person names supplied in a denylist. Allow vendor/application names supplied in an allowlist. Return allowed, sanitized, or blocked with reason.

Do not call web search. Do not use an LLM as final authority. Add unit tests.
```

## Phase 4 - Source Ranker
```text
Implement source ranking based on source_policy.md. Create verified_memory/verification/source_ranker.py. Classify sources into official_vendor, official_release_notes, official_github, government_or_institution, trusted_technical_blog, wikipedia_background, forum_or_reddit, unknown, blocked_low_quality. Start with deterministic URL/domain rules. Add tests. Do not call web search yet.
```

## Phase 5 - Document Ingestion
```text
Implement local document ingestion for markdown and plain text first. Load .md and .txt files. Split into stable chunks. Preserve source document path, document name, line start, and line end. Store chunks in SQLite. Do not summarize yet. Do not use embeddings yet. Add tests.
```

## Phase 6 - Local Ask Context Package
```text
Implement ask_with_verified_memory. Accept a user question, search local chunks and memory claims using keyword search, run staleness check, and return a structured context package. Do not produce final AI answer yet. Do not call web search. Do not call LLM. Add tests.
```

## Phase 7 - LLM Answer Integration
```text
Integrate ask_with_verified_memory with the existing Odysseus model call layer. Build a prompt containing user question, retrieved fresh claims, stale claims clearly marked stale, source chunks, citation instructions, and no-invented-citations rule. Return final answer plus cited source_refs. Do not use web search yet.
```

## Phase 8 - Manual Web Verification
```text
Implement manual web verification for one memory claim. Load claim, check allowed_web_search, generate generic query, pass through query_sanitizer, block if unsafe, search using existing Odysseus integration if available, rank sources, return verification candidates, and create candidate update. Do not overwrite memory automatically.
```
