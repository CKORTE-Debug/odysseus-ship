# Companion integration foundation

The executable Python contracts are in
`verified_memory/contracts/project_contract.py` (contract version `1.0`).
The current design/code handoff is maintained in the
[canonical integration blueprint](https://docs.google.com/document/d/1uXB_uZt9XGLHBCQ7olNTaq14x4tpuxB5TMBPvGbcVp4).

## Composition

An authenticated adapter constructs `RequestScope`; a model or request body
must never select `actor_id` or a database path. `VerifiedMemoryWorkspace`
resolves scope to a hashed, application-owned directory and verifies the
stored identity. Project creation and checkpoint initialization are explicit.

```python
from companion_core import (
    CompanionKernel, LocalModelGateway, OdysseusLocalAdapter, SQLiteCheckpointStore,
)
from verified_memory.contracts.project_contract import EvidenceQuery, RequestScope
from verified_memory.service import VerifiedMemoryWorkspace

# These values come from trusted application configuration/authentication.
scope = RequestScope(authenticated_owner, selected_project)
workspace = VerifiedMemoryWorkspace(configured_memory_directory)
memory = workspace.open_project(scope)
journal = SQLiteCheckpointStore(configured_checkpoint_path)
models = LocalModelGateway(memory, {
    "local": OdysseusLocalAdapter(configured_loopback_url, configured_model),
})
kernel = CompanionKernel(scope, memory, models, journal)
# In an async handler owned by the supervised task workflow:
result = await kernel.run(
    "design-review-1", EvidenceQuery(question, context_budget_chars=64000), "local",
)
```

Installer/setup code uses `workspace.create_project(scope)` and
`SQLiteCheckpointStore.create(path)` before opening these resources. The UI
creates its selected memory project through an explicit POST. Import an
owner-approved `procedure` and `current_state` record before running a kernel
task. Reimport unchanged text to record a new local import observation without
changing the immutable content revision.

## Boundaries and behavior

- `MemoryPort`: prepare context, recheck it, and validate citation/heuristic
  output through `VerifiedMemoryService`. The kernel does not touch memory SQL.
- `ModelPort`: one bounded call. The initial adapter reuses `src.llm_core`,
  permits configured loopback endpoints only, and has no provider fallback.
  Tests inject a deterministic adapter callback; they do not prove model quality.
- `CheckpointPort`: separate SQLite journal with scoped compare-and-swap
  versions. Resume is explicit; each task has at most two attempts. Output waits
  in `review_required` and is not automatically approved or integrated.
- Context includes required approved records independently of keyword ranking.
  All active source revisions contribute to an invalidation fingerprint. Both
  scope/content tampering and source changes during generation reject output.
- Freshness means local import-observation age. The foundation does not check
  live Google Drive revisions. External adapters must provide a trusted refresh
  mechanism before claiming stronger freshness.
- `claim_support=not_evaluated` is deliberate. A permitted citation does not
  prove semantic entailment or factual truth.

The kernel is wired into Brain → Evidence → Local project step through
`ProjectCompanionService` and `routes/project_companion_routes.py`. Existing
ordinary chats keep their current path. This is a supervised step primitive,
not the M5 lease/DAG scheduler or an autonomous coding agent.
Private task results stay in the local journal. No production deployment or
automatic Git operations are performed by this code.

## Application workflow

Open/create a project in Brain → Evidence, import approved `procedure` and
`current_state` records, and configure an enabled loopback chat endpoint in
the existing Odysseus model settings. Its cached or pinned model list must
contain the selected model. Click **Enable local project steps**, select the
model, enter a question and run it. Output retains source-revision references
for inspection and waits for **Mark reviewed** or **Reject output**. Reviewing
an output records a human decision; it does not promote factual memory or
modify canonical records.

`ConfiguredLocalModels` filters by authenticated owner or legacy shared
ownership, enabled state, loopback URL and chat model. It does not probe,
refresh OAuth, list API keys, select a cloud provider or silently fall back.
Credentials are loaded only for an eligible explicit selection and passed
in memory to `llm_core`; they are absent from task checkpoints.

The route prefix is `/api/project-companion/projects/{project_id}`:

| Method | Path | Operation |
| --- | --- | --- |
| POST | `/initialize` | Explicitly create the local checkpoint journal |
| GET | `/models` | Read configured eligible models without probing |
| GET | `/tasks` | Read 30 recent scoped task summaries |
| POST | `/tasks` | Queue an immutable question/model request with client task ID |
| GET | `/tasks/{task_id}` | Read status, output, provenance and checkpoint version |
| POST | `/tasks/{task_id}/cancel` | Cancel/pause using `expected_version` |
| POST | `/tasks/{task_id}/resume` | Explicitly retry the saved request, at most two attempts |
| POST | `/tasks/{task_id}/review` | Record `acknowledged` or `rejected` using `expected_version` |

All routes use the same trusted browser-to-project identity helper as memory.
The body cannot set identity, storage paths or endpoint URLs. Start is
idempotent for an identical task ID/request; reusing an ID for a changed
request is a conflict. Concurrent updates require refresh after HTTP 409.

One model call runs at a time per app process, with at most eight queued/live
handles. Run one application worker for this initial runner. Multiple worker
processes do not share its semaphore or handles; adding durable leases and
cross-process resource reservations is a separate milestone. After a crash,
persisted queued/running tasks show as interrupted and require explicit
resume. Cancellation cannot guarantee an upstream serving process stops GPU
work immediately. No model call has tools or automatic canonical write access.

Memory and journal defaults honor the existing `ODYSSEUS_DATA_DIR` through
`src.constants.DATA_DIR`. `VERIFIED_MEMORY_DATA_DIR` and `COMPANION_DATA_DIR`
are optional trusted operator overrides. Missing projects/journals are never
created by read requests. Existing legacy stores are not moved automatically.

## Verification

```bash
python -m pytest tests/verified_memory tests/test_memory_provider.py \
  tests/test_memory_routes_session_owner.py tests/test_memory_owner_isolation.py \
  tests/test_workspace_confine.py -q
python scripts/evaluate_verified_memory.py
node --check static/js/verified-memory.js
node --check static/js/project-companion.js
# Optional development dependencies: Node + happy-dom, beautifulsoup4, uvicorn.
# Set HAPPY_DOM_MODULE to a file: URL of happy-dom's ESM entry if needed.
python scripts/smoke_project_evidence.py
```

See `docs/verified-memory/12_Integration_Foundation_Validation.md` for the
recorded environment, test scope, migration effects and pending release checks.
