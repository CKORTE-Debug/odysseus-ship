# Integration foundation validation — 2026-11-03

Status: tested development candidate; independent review and host release gate pending.
Base: `dev` at `b98b6d747677116c250e266e24a99ceb6825f015`.

## Actual checks

- Original Verified Memory baseline: 252 passed, 1 failed. The failure used a
  fixed June 2026 verification date without freezing the current clock, so its
  expected fresh claim expired. An optional `now` parameter and explicit test
  clock fix this reproducibly. The original suite then passed 253 tests.
- Selected legacy memory/owner/workspace baseline: 30 passed.
- Final combined targeted suite: **298 passed**, no failures or skips, in the
  recorded Linux/Python environment. The v2 route tests intentionally replace
  the retired path-based API tests, so counts are not directly comparable.
- New Python files pass Ruff checks. JavaScript passes `node --check` and
  Python modules compile. `git diff --check` passes.
- Synthetic retrieval benchmark: 30/30 development cases and 10/10 reserved
  cases pass; all 18 critical cases and source-integrity checks pass. The
  reserved subset was authored alongside the development subset. This is a
  small regression fixture, not independent evidence of general accuracy.
- Happy DOM plus the real scoped FastAPI/SQLite routes: project creation,
  UTF-8 source import, passage query, literal rendering of hostile markup,
  original-source inspection, approved-record import, context preflight and
  clearing previous-project output all passed.

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

Full Windows application startup, visual browser layout/accessibility,
symlink/junction behavior on Windows, live local-model inference, complete
repository CI and independent code/security review remain pending.
The Chromium download in this environment returned invalid archives, so the
DOM checks must not be described as rendered browser verification.

No cloud-provider routing, live Drive sync, automatic conflict inference,
semantic claim verification, external MCP adapter, DAG/lease scheduling,
autonomous coding or release deployment is delivered by this foundation.
Those remain later integration tasks. The full M1 release gate is not closed.
