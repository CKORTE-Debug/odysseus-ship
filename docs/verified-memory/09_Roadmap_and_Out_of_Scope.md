# 09 - Roadmap and Out of Scope

## Purpose
This document keeps the project from expanding too quickly. Codex should follow the roadmap unless explicitly instructed otherwise.

## Current state from repository inspection
Odysseus already has:

- Legacy JSON memory.
- ChromaDB vector memory.
- Web/search/research services.
- LLM abstraction in `src.llm_core`.
- Pytest test framework.

Verified Memory should not replace these immediately. It should be built as a standalone tested layer first.

## Roadmap

### Milestone 0: Planning and inspection
Status: complete.

Deliverables:

- Repo inspection report.
- Planning docs.
- Operating instructions.
- Policies.

Exit criteria:

- No code changed.
- Integration points identified.

### Milestone 1: Standalone data model and SQLite store
Goal: Create the safe foundation.

Deliverables:

- `verified_memory` module.
- `MemoryClaim`, `SourceRef`, `ConflictRecord` models.
- SQLite storage.
- Round-trip tests.

Strict limits:

- No UI.
- No web search.
- No LLM calls.
- No ChromaDB integration.
- No legacy memory migration.

### Milestone 2: Policy primitives
Goal: Implement deterministic guardrails.

Deliverables:

- Staleness engine.
- Query sanitizer.
- Source ranker.
- Policy decision objects.
- Unit tests.

Strict limits:

- Query sanitizer must run before any search later.
- LLM must not enforce privacy.
- No network tests.

### Milestone 3: Domain profiles
Goal: Make the system useful beyond IT.

Deliverables:

- Domain profile schema.
- Default profile.
- IT/software profile.
- General business profile.
- Tests for domain staleness/source rules.

Optional later profiles:

- Legal.
- Medical.
- Finance.
- Academic.
- Gaming.
- Personal knowledge.

### Milestone 4: Local document ingestion
Goal: Preserve local evidence.

Deliverables:

- `.md` and `.txt` document loader.
- Chunker with stable chunk IDs.
- Line references.
- Document chunk storage.
- Tests.

Strict limits:

- No PDF/DOCX until text ingestion is solid.
- No embeddings until source refs are stable.

### Milestone 5: Candidate claim extraction
Goal: Convert source chunks into candidate memory claims.

Deliverables:

- Simple heuristic claim extractor.
- Candidate claims with source refs.
- Low confidence/unverified default.
- Tests.

Optional later:

- LLM-assisted extraction using Odysseus model layer.

### Milestone 6: Local ask context package
Goal: Retrieve evidence for a question without generating the final answer yet.

Deliverables:

- Keyword retrieval.
- Matching memory claims.
- Matching document chunks.
- Staleness labels.
- Conflict warnings.
- Structured context package.
- Tests.

Strict limits:

- No final LLM answer yet.

### Milestone 7: Manual web verification
Goal: Safely verify one claim online.

Deliverables:

- Refresh one memory claim by ID.
- Generate generic query.
- Sanitize/block query.
- Call existing Odysseus search only after sanitizer.
- Rank sources.
- Create verification run and candidate update.
- Tests with fake search provider.

Strict limits:

- No automatic overwrite.
- No nightly refresh.
- No private data search.

### Milestone 8: Conflict detection
Goal: Prevent silent memory poisoning.

Deliverables:

- Basic conflict detector.
- Conflict records.
- Candidate update workflow.
- Approval requirement for overwrites.
- Tests.

### Milestone 9: LLM answer integration
Goal: Generate answers using verified context.

Deliverables:

- Integration through `src.llm_core`.
- Prompt builder with fresh/stale/unverified labels.
- Citation constraints.
- Final answer format.
- Tests/mocks.

Strict limits:

- Final answer cannot invent source refs.
- Stale claims cannot be stated as confirmed.

### Milestone 10: Odysseus UI/API integration
Goal: Make it usable in the app.

Deliverables:

- Backend route or service wrapper.
- Minimal UI or CLI control.
- Inspect memory claim.
- Refresh memory.
- View conflicts.
- Approve/reject candidate update.

Strict limits:

- Keep UI minimal.
- Do not redesign Odysseus.

### Milestone 11: Vector search integration
Goal: Improve retrieval after evidence model is stable.

Deliverables:

- Optional ChromaDB adapter.
- Embeddings tied to `DocumentChunk`/`MemoryClaim` IDs.
- Tests proving source refs remain intact.

Strict limits:

- Vector result cannot be treated as evidence unless linked to stored source chunk.

### Milestone 12: Refresh queue / nightly refresh
Goal: Refresh watched public topics.

Deliverables:

- Refresh queue.
- Watched claim settings.
- Scheduled refresh report.
- Audit log.

Strict limits:

- No silent overwrite.
- Public/safe-to-search claims only.
- Private/client-confidential claims require manual approval.

## Out of scope until explicitly approved
- Replacing existing Odysseus memory.
- Migrating legacy memory to verified memory.
- Full enterprise permission model.
- Multi-user role-based access control.
- Automatic web browsing from private context.
- Automatic memory overwrite.
- Unattended nightly refresh of private/client-confidential data.
- Full PDF/DOCX OCR pipeline.
- Legal/medical/financial professional advice automation.
- Fancy UI redesign.
- Distributed agent swarm architecture.
- Using deep research as a dependency for early primitives.

## Immediate next Codex task recommendation
Start Milestone 1 only:

> Implement standalone `verified_memory` data models and SQLite storage with tests. No web, no LLM, no UI, no ChromaDB, no legacy memory changes.

## Stop conditions
Codex should stop and report instead of coding if:

- It needs to modify existing memory/search/LLM behavior for Milestone 1.
- It cannot determine existing test conventions.
- It finds an existing module named `verified_memory`.
- It must add a new dependency not already present.
- It cannot run the relevant tests.
