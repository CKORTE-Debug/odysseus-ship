# Odysseus Verified Memory Fork

## Purpose
Build a local-first verified memory layer for an Odysseus fork. Store AI memory as source-linked, timestamped claims with staleness, privacy, verification, and conflict metadata. First goal: reliable backend feature, not polished UI.

## Core Product Thesis
- Local AI is useful when it is private, source-grounded, and refreshable.
- Memory must not be vague. Each claim needs evidence, date, confidence, sensitivity, and freshness state.
- Web confirmation should be allowed only through a privacy-safe query gate and source-priority policy.
- Stale memories are leads, not truth, until refreshed or reconfirmed.
- Prefer slow, careful, auditable workflows over fast ungrounded answers.

## High-Level Architecture
```text
User question -> task classifier -> local retrieval -> staleness/sensitivity check -> optional sanitized web verification -> source ranking/evidence comparison -> conflict detection/candidate update -> final answer with citations -> optional memory update after approval
```

## Roadmap
| Milestone | Goal | Deliverable | Do not include yet |
|---|---|---|---|
| 0 | Inspect Odysseus architecture | Integration map and risk notes | Code changes |
| 1 | Standalone memory schema + SQLite | Models, store, schema tests | LLM, network, UI |
| 2 | Staleness engine | Fresh/stale/unverified/invalid checks | Web refresh |
| 3 | Privacy-safe query sanitizer | Deterministic blocker/sanitizer tests | LLM-based security |
| 4 | Source priority ranking | Deterministic domain/source ranker | Full web search |
| 5 | Document ingestion | TXT/MD chunks with line refs | PDF/DOCX/OCR |
| 6 | Local retrieval workflow | Context package with warnings | Final AI answer |
| 7 | LLM answer integration | Source-cited answer prompt | Web verification |
| 8 | Manual web refresh | Candidate update, no overwrite | Nightly automation |
| 9 | Conflict detection | Conflict records and review flow | Silent mutation |

## Definition of Done
- Every module has unit tests.
- No network access before web verification milestone.
- No private data can pass query sanitizer tests.
- Memory updates are proposals first.
- Answers cite only retrieved source references.
- CLI works before UI.
