# Codex Operating Instructions

## Standing Instruction
You are working on an Odysseus fork.

Rules:
1. Make the smallest possible change.
2. Do not rewrite unrelated files.
3. Add or update tests for every behavior change.
4. Prefer deterministic code for privacy, source ranking, staleness, and schema validation.
5. Do not rely on the LLM to enforce security rules.
6. Do not add network calls unless explicitly requested.
7. Do not overwrite existing memory automatically.
8. Preserve source references and timestamps.
9. If unsure, inspect and report before coding.
10. Run relevant tests and summarize results.

## Security Rules
- Online search is blocked by default for private, client-confidential, or personal-sensitive memory.
- The LLM may propose a search query, but deterministic code must approve, sanitize, or block it.
- Never send local document text directly into a search query.
- Never include client names, employee names, emails, internal domains, IPs, hostnames, ticket numbers, file paths, internal filenames, or project codenames in web search.
- Allow vendor/application names only when they are the maker/provider of the software or product being researched.

## Required Codex Response Format
For every task, respond with:
1. Summary of files changed.
2. Why each change was necessary.
3. Tests added or updated.
4. Test command run and result.
5. Risks, TODOs, or assumptions.
6. Confirmation that no unrelated files were changed.
