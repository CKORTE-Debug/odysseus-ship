# Integration foundation validation — 2026-11-03

Status: tested development candidate; independent review and host release gate pending.
Base: `dev` at `b98b6d747677116c250e266e24a99ceb6825f015`.

## Actual checks

- Original Verified Memory baseline: 252 passed, 1 failed. The failure used a
  fixed June 2026 verification date without freezing the current clock, so its
  expected fresh claim expired. An optional `now` parameter and explicit test
  clock fix this reproducibly. The original suite then passed 253 tests.
- Selected legacy memory/owner/workspace baseline: 30 passed.
- Final combined targeted suite after app integration/self-review: **341 passed**, no failures or skips, in the
  recorded Linux/Python environment. The v2 route tests intentionally replace
  the retired path-based API tests, so counts are not directly comparable.
- New Python files pass Ruff checks. JavaScript passes `node --check` and
  Python modules compile. `git diff --check` passes.
- Synthetic retrieval benchmark: 30/30 development cases and 10/10 reserved
  cases pass; all 18 critical cases and source-integrity checks pass. The
  reserved subset was authored alongside the development subset. This is a
  small regression fixture, not independent evidence of general accuracy.
- Happy DOM plus real scoped FastAPI/SQLite routes: **17 workflow checks**
  passed, including source import/query/inspection, approved-context preflight,
  local output waiting for review, safe rendering of source and model markup,
  output provenance, acknowledgement/rejection, running cancellation, explicit
  second-attempt resume, and ignoring a delayed prior-project query.
- A loopback HTTP protocol fixture exercises the actual configured-model
  registry → kernel → `src.llm_core` HTTP client → review checkpoint path.
  It confirms one request, the expected model/path, credential forwarding and
  absence of keys in checkpoints. This is not real-model inference.
- The full Linux app imports successfully with a disposable data directory
  and in-memory main DB. Host proxy variables were removed for that isolated
  import because this environment lacks optional SOCKS support. ChromaDB,
  python-magic and YouTube transcript integration were reported unavailable.
  This check did not execute full app startup/shutdown or authenticate a user.

The test client supplies trusted identity state equivalent to the app's auth
middleware. Real route-level authorization helpers and SQLite stores run;
the full application's authentication startup is not covered by that fixture.
The repository conftest retains its existing optional-module stubs. The new
memory/kernel behavior runs real code; model tests use injected callbacks.

## Environment

Linux, Python 3.12.14; pytest 9.2.0; FastAPI 0.162.0; Starlette 1.10.0;
Pydantic 2.14.2; httpx 0.28.1; SQLAlchemy 2.1.6; Ruff 0.17.3.
Dependencies were installed in an isolated development environment. No new
runtime dependency is required by the added core modules.

The commands are listed in `companion_core/README.md`. The evaluator is
`python scripts/evaluate_verified_memory.py` and performs no network/model calls.

## API migration

HTTP requests no longer accept `db_path` or filesystem `path` fields.
Use `POST /api/verified-memory/projects`, then upload text to
`POST /api/verified-memory/projects/{project_id}/sources`.
The request owner is derived from existing authenticated request state.
Browser-owned project data rejects bearer tokens until a scope-aware external
adapter is implemented. Other users cannot select the source owner's namespace.

The old `/admin/ingest` and `/admin/extract-claims` operations require admin
authorization and return HTTP 410. Standalone local operator CLI/service use
is retained. Existing legacy memory data is not migrated or replaced.

Read paths open an existing scoped database in SQLite read-only mode. Source
imports atomically retain original text and revision chunks. Source replacement
uses explicit effective time; historical inspection uses effective time, not a
complete bitemporal “what was known then” query.

## Pending checks and scope

Self-review additionally fixed reactivation of older document content,
transactional idempotency for simultaneous uploads, conflicting external
revision identities, invalid project IDs returning server errors, and unknown
prepared-context contract versions. Regression tests cover those cases.
This author review does not replace the independent release review.

The application increment also fixed early task cancellation before coroutine
entry, stale UI responses after project/task selection changes, stale error
metadata on retry and model-list reads unnecessarily loading API keys. The
new lifecycle tests cover idempotent start, immutable saved request, explicit
restart recovery, two-attempt limits, queued cancellation, one active call,
eight-handle capacity, model ownership, OAuth/cloud exclusion and review CAS.
`scripts/smoke_project_evidence.py` provides the reproducible DOM harness.

Full Windows application startup, visual browser layout/accessibility,
symlink/junction behavior on Windows, live local-model inference, complete
repository CI and independent code/security review remain pending.
The Chromium download in this environment returned invalid archives, so the
DOM checks must not be described as rendered browser verification.

No cloud-provider routing, live Drive sync, automatic conflict inference,
semantic claim verification, external MCP adapter, DAG/lease scheduling,
autonomous coding or release deployment is delivered by this foundation.
Those remain later integration tasks. The full M1 release gate is not closed.
