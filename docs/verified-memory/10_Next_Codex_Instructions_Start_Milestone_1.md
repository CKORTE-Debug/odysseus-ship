# 10 - Next Codex Instructions: Start Milestone 1

Use this prompt after committing the planning documents into the Odysseus fork.

## Codex prompt

Read these files first:

- `docs/verified-memory/01_Project_Plan_Odysseus_Verified_Memory.md`
- `docs/verified-memory/02_Codex_Operating_Instructions.md`
- `docs/verified-memory/03_Codex_Prompt_Pack_and_Checklists.md`
- `docs/verified-memory/04_Product_Requirements.md`
- `docs/verified-memory/05_Architecture_and_Data_Model.md`
- `docs/verified-memory/06_Threat_Model_and_Privacy_Guardrails.md`
- `docs/verified-memory/07_Domain_Profile_System.md`
- `docs/verified-memory/08_Testing_and_Acceptance_Criteria.md`
- `docs/verified-memory/09_Roadmap_and_Out_of_Scope.md`
- `docs/verified-memory/source_policy.md`
- `docs/verified-memory/privacy_policy.md`
- `docs/verified-memory/staleness_policy.md`

Follow `02_Codex_Operating_Instructions.md` as standing rules.

Start Milestone 1 only.

## Task

Implement standalone `verified_memory` data models and SQLite storage with tests.

## Scope allowed

Create a new standalone module, preferably:

```text
verified_memory/
  __init__.py
  models/
    __init__.py
    memory_claim.py
    source_ref.py
    conflict_record.py
  storage/
    __init__.py
    sqlite_store.py
```

Create tests under:

```text
tests/verified_memory/
  test_memory_schema.py
  test_sqlite_store.py
```

## Data models required for Milestone 1

Implement:

- `MemoryClaim`
- `SourceRef`
- `ConflictRecord`

Minimum `MemoryClaim` fields:

- `id`
- `claim`
- `claim_type`
- `source_refs`
- `created_at`
- `last_verified_at`
- `stale_after_days`
- `status`
- `confidence`
- `sensitivity`
- `verification_policy`
- `allowed_web_search`
- `domain`
- `superseded_by`
- `conflicts_with`

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

Minimum `SourceRef` fields:

- `source_id`
- `source_type`
- `document_name`
- `path`
- `page`
- `line_start`
- `line_end`
- `chunk_id`
- `quote`
- `url`
- `retrieved_at`
- `source_rank`

Minimum `ConflictRecord` fields:

- `id`
- `claim_ids`
- `description`
- `created_at`
- `severity`
- `status`
- `resolution`

Allowed `severity` values:

- `low`
- `medium`
- `high`

Allowed conflict `status` values:

- `open`
- `resolved`
- `ignored`

## SQLite storage requirements

Implement create/read/update/list operations for memory claims.

Required behavior:

- Save a `MemoryClaim` with one or more `SourceRef` objects.
- Load the claim and preserve all fields.
- Update status/confidence/sensitivity.
- List claims.
- Store conflict records if simple to include in this phase; otherwise create the model and leave storage TODO clearly documented.
- Use a temporary SQLite database in tests.

## Strictly forbidden in this task

Do not:

- Modify existing Odysseus legacy memory behavior.
- Modify `src/memory.py`.
- Modify existing web/search/research behavior.
- Call web search.
- Call any LLM.
- Add UI routes.
- Add ChromaDB/vector integration.
- Add new external dependencies unless absolutely necessary and approved.
- Migrate `memory.json`.

## Required tests

Add tests proving:

- Valid `MemoryClaim` can be created.
- Invalid status is rejected.
- Invalid confidence is rejected.
- Invalid sensitivity is rejected.
- `stale_after_days = None` is accepted.
- A claim with source refs round-trips through SQLite.
- Updated claim status persists.
- Listing claims works.

## After coding

Run only relevant tests first:

```bash
pytest tests/verified_memory -q
```

Then report:

1. Files changed.
2. Why each change was necessary.
3. Tests added.
4. Test results.
5. Any risks/TODOs.
6. Confirmation that no web/LLM/UI/search/legacy memory behavior was changed.

Do not continue to Milestone 2 until I explicitly approve.
