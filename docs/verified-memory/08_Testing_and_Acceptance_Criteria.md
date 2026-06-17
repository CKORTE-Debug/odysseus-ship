# 08 - Testing and Acceptance Criteria

## Purpose
This project is only useful if it is trustworthy. Passing tests is not optional; every phase must include tests before moving on.

The goal is not only to prevent crashes. The goal is to prevent false trust, privacy leaks, bad citations, stale-memory misuse, and silent memory corruption.

## General test rules for Codex
- Add or update tests for every behavior change.
- Prefer deterministic unit tests before integration tests.
- Do not add network-dependent tests in early phases.
- Do not require real API keys for tests.
- Use fixtures and fake search providers for verification tests.
- Test negative cases as carefully as success cases.

## Test categories

### 1. Schema tests
Required for:

- `MemoryClaim`
- `SourceRef`
- `DocumentChunk`
- `VerificationRun`
- `ConflictRecord`
- `DomainProfile`
- `PolicyDecision`

Acceptance criteria:

- Valid records can be created.
- Invalid enum values are rejected.
- Required fields are enforced.
- Datetimes are parsed consistently.
- JSON serialization/deserialization works.

Example tests:

```text
MemoryClaim rejects invalid status.
MemoryClaim rejects invalid confidence.
MemoryClaim allows stale_after_days = null.
SourceRef preserves line_start and line_end.
```

### 2. SQLite storage tests
Acceptance criteria:

- Claims can be created, read, updated, listed, and deleted/archived if supported.
- Source refs round-trip correctly.
- Conflicts and verification runs round-trip correctly.
- Partial writes do not corrupt records.
- Storage works in a temporary test database.

Example tests:

```text
Save claim with two source refs, load it, compare all fields.
Update claim status from unverified to verified.
Create verification run linked to claim.
Create conflict record linked to two claims.
```

### 3. Staleness tests
Acceptance criteria:

- Fresh memory is fresh.
- Old memory is stale.
- Missing `last_verified_at` is unverified.
- `stale_after_days = null` means never stale.
- Future `last_verified_at` is invalid.
- Domain profile staleness overrides defaults.

Example tests:

```text
Software claim verified 61 days ago with stale_after_days 60 is stale.
Personal preference with stale_after_days null is never_stale.
Missing verification date is unverified.
Future verification date is invalid.
```

### 4. Query sanitizer tests
Acceptance criteria:

- Private data is blocked or removed.
- Vendor/application names are allowed.
- Sanitizer returns structured `PolicyDecision`.
- The network/search layer cannot be reached if sanitizer blocks.

Required blocked examples:

```text
user@example.com Teams error
192.168.10.22 Intune enrollment issue
INC123456 Autopilot failure
/Users/christopher/client_docs/private_sop.md Microsoft 365 issue
client.local SharePoint issue
```

Required allowed examples:

```text
Microsoft Intune Autopilot OOBE Wi-Fi driver missing
Adobe Acrobat Japanese language pack install
Surface Laptop 5 Windows 11 drivers
```

Required sanitized examples:

```text
Input: ClientName John Smith Teams folder hidden
Output: Microsoft Teams folder visible by direct link not shown in Files tab SharePoint permissions
```

### 5. Source ranker tests
Acceptance criteria:

- Official sources rank above blogs/forums.
- Wikipedia is background only.
- Reddit/forums are clue-only by default.
- Unknown sources do not become authoritative.

Example tests:

```text
learn.microsoft.com -> official_vendor
support.microsoft.com -> official_vendor
github.com/microsoft/... -> official_github
wikipedia.org -> wikipedia_background
reddit.com -> forum_or_reddit
random-seo-blog.example -> unknown
```

### 6. Document ingestion tests
Acceptance criteria:

- `.md` and `.txt` load correctly.
- Chunks preserve document ID, path, chunk ID, text, line start, and line end.
- Chunk IDs are stable across repeated ingestion if content is unchanged.
- Original source text is preserved.

Example tests:

```text
Markdown with headings and bullets creates expected chunks.
Line references match original file.
Re-ingesting unchanged file does not duplicate chunks unexpectedly.
```

### 7. Claim extraction tests
For early versions, claim extraction may be heuristic.

Acceptance criteria:

- Bullet lines with `must`, `should`, `requires`, `do not`, or `if` can produce candidate claims.
- Candidate claims are `unverified` or `low` confidence by default.
- Candidate claims include source refs.

### 8. Conflict tests
Acceptance criteria:

- Contradictory claims create `ConflictRecord`.
- Newer evidence does not overwrite older memory automatically.
- Low-quality sources cannot overwrite high-quality sources.
- Conflict resolution requires explicit update.

Example tests:

```text
Old SOP says create local account.
New SOP says follow Autopilot after Wi-Fi.
Expected: conflict record, no automatic overwrite.
```

### 9. Verification workflow tests
Use fake search providers first.

Acceptance criteria:

- Sanitizer runs before search.
- Blocked query creates `blocked_by_privacy` verification result.
- Allowed query reaches fake search provider.
- Source ranker ranks fake results.
- Candidate update is created, not applied.

### 10. LLM integration tests
Only after deterministic context package is stable.

Acceptance criteria:

- Prompt includes fresh/stale/unverified labels.
- Stale memory is not presented as confirmed.
- Final answer may only cite provided source refs.
- If no reliable source is found, answer says so.

## Phase acceptance gates

### Gate 1: Standalone storage complete
Pass when:

- Models exist.
- SQLite store exists.
- Round-trip tests pass.
- No web/LLM/UI code added.

### Gate 2: Policy primitives complete
Pass when:

- Staleness tests pass.
- Query sanitizer tests pass.
- Source ranker tests pass.
- No network calls happen in tests.

### Gate 3: Local evidence complete
Pass when:

- Document ingestion tests pass.
- Chunk references are stable.
- Candidate claims preserve source refs.

### Gate 4: Manual verification complete
Pass when:

- Sanitizer blocks private queries.
- Fake search test proves search is after sanitizer.
- Candidate update and verification run records are created.
- No automatic overwrite.

### Gate 5: Odysseus integration ready
Pass when:

- Context package is deterministic.
- LLM integration uses `src.llm_core`.
- Existing legacy memory behavior is unchanged.
- Regression tests pass.

## Code review checklist
Before accepting Codex changes, verify:

- No unrelated files were modified.
- Tests were added or updated.
- No network calls were added unless explicitly requested.
- No LLM calls were added unless explicitly requested.
- Privacy policy enforcement is deterministic.
- Existing Odysseus memory/search behavior is not broken.
- Source refs remain intact.
- Stale/unverified claims are clearly labeled.
