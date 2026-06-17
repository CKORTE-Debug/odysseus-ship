# 04 - Product Requirements: Odysseus Verified Memory

## Purpose
Verified Memory is a local-first evidence and memory layer for an Odysseus fork. It stores AI-usable knowledge as source-linked, timestamped claims rather than vague freeform notes.

The project should help an AI assistant answer using local/private knowledge while reducing the risk of stale information, unsupported claims, privacy leaks, and bad source use.

## Repository context from inspection
Codex inspection found that Odysseus currently has:

- Legacy/simple memory in `src/memory.py` backed by `DATA_DIR/memory.json`.
- Basic memory fields such as `id`, `text`, `timestamp`, `source`, `category`, and usage counters.
- Web/search/research infrastructure already available, including search providers and research tools.
- No deterministic verified-memory privacy gate before web search.
- Existing LLM abstraction in `src/llm_core.py`.
- ChromaDB vector memory in `src/memory_vector.py`, but without source-linked verification metadata.

Therefore, Verified Memory should start as a standalone module and avoid modifying existing memory/search/LLM behavior in early phases.

## Core product statement
Verified Memory adds an evidence-aware memory system to Odysseus:

> Every reusable memory should know what it claims, where it came from, how trustworthy it is, how sensitive it is, when it was last checked, and whether it is stale or contradicted.

## Primary users

### Technical local-AI users
Users who want a private/local AI workspace but need better accuracy and source tracking.

### IT and operations users
Users handling SOPs, troubleshooting notes, software behavior, client documentation, and system procedures.

### Knowledge workers in other industries
Users in legal, finance, health, research, education, gaming/community knowledge, or general business who need domain-specific source and staleness rules.

## User modes

### Fast Mode
Use local verified-memory retrieval quickly. Warn if relevant memories are stale or unverified. No online verification.

### Careful Mode
Check local memories, source references, sensitivity, staleness, and conflicts before answering. No online verification unless explicitly requested.

### Verified Mode
For public or safe-to-search claims, confirm stale or uncertain information online using privacy-safe search and source-priority rules. Never send private document text to web search.

### Private Mode
Use local sources only. Never call web search. Never call external APIs unless the user explicitly chooses an API model.

## Required capabilities

### Version 0.1 capabilities
- Standalone `verified_memory` module.
- Structured `MemoryClaim` model.
- Structured `SourceRef` model.
- SQLite storage independent of legacy `memory.json`.
- Staleness evaluation.
- Unit tests for schema and storage.

### Version 0.2 capabilities
- Deterministic query sanitizer.
- Source ranker based on source priority policies.
- Domain profile data model.
- Tests for privacy, source ranking, and staleness.

### Version 0.3 capabilities
- Local document ingestion for `.md` and `.txt`.
- Chunking with stable chunk IDs and line references.
- Candidate claim extraction from local chunks.
- Local ask context package with source references.

### Version 0.4 capabilities
- Manual web verification for one claim at a time.
- Privacy gate before all web search.
- Candidate update records, not automatic overwrite.
- Conflict detection.

### Version 0.5 capabilities
- Odysseus LLM answer integration through `src.llm_core`.
- Prompt context package with fresh/stale/unverified/conflicting evidence labels.
- Final answer citations based only on provided `SourceRef` values.

### Version 0.6+ capabilities
- UI integration.
- Optional vector search integration after source references are stable.
- Optional refresh queue / nightly refresh for watched public topics.

## Non-goals
- Do not replace Odysseus legacy memory in early phases.
- Do not mutate existing search behavior globally.
- Do not use deep research for early verification primitives.
- Do not overwrite memory automatically.
- Do not send private local documents to online search.
- Do not build a fancy UI before backend behavior is reliable.
- Do not claim verified truth when evidence is stale, weak, or contradictory.

## Key user stories

### Store source-linked memory
As a user, I want the AI to store important facts with exact source references so I can trust where the memory came from.

### Detect stale memory
As a user, I want old software/pricing/news memories to be treated as stale until verified.

### Avoid private-data leakage
As a user, I want online verification to remove or block client names, employee names, emails, IPs, internal domains, and private file names.

### Prefer authoritative sources
As a user, I want official vendor/government/institution sources prioritized over blogs, forums, Reddit, and SEO pages.

### Support multiple industries
As a user, I want different domains to have different source priorities, staleness windows, and privacy rules.

### Prevent silent memory corruption
As a user, I want new evidence to create candidate updates and conflict records rather than silently overwriting old memory.

## Success criteria
- A memory claim cannot be treated as verified without a source reference or explicit user-provided status.
- Stale memory is never presented as fresh.
- A blocked private search query cannot reach the existing Odysseus search stack.
- Manual refresh creates an auditable verification record.
- Forum/Reddit results cannot overwrite official sources.
- LLM-generated summaries never replace original source chunks.
- All critical behavior has pytest coverage.
