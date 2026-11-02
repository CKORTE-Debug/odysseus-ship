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

The new kernel is not wired into every existing chat path. This is a supervised
step primitive, not the M5 lease/DAG scheduler or an autonomous coding agent.
Private task results stay in the local journal. No production deployment or
automatic Git operations are performed by this code.

## Verification

```bash
python -m pytest tests/verified_memory tests/test_memory_provider.py \
  tests/test_memory_routes_session_owner.py tests/test_memory_owner_isolation.py \
  tests/test_workspace_confine.py -q
python scripts/evaluate_verified_memory.py
node --check static/js/verified-memory.js
```

See `docs/verified-memory/12_Integration_Foundation_Validation.md` for the
recorded environment, test scope, migration effects and pending release checks.
