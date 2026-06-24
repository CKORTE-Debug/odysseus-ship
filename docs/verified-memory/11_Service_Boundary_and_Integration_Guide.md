# 11 - Service Boundary and Integration Guide

## Purpose

`VerifiedMemoryService` is the only app-facing service boundary for verified-memory operations. Future API routes, UI components, CLI adapters, or other application code should call this service instead of importing lower-level workflows directly.

The service exists to keep the safety contract understandable and hard to misuse: local evidence must be retrieved, prompts must be built from that evidence, model output must be validated, and generated answers must not be shown unless validation metadata says they are safe.

## Why use the service instead of lower-level workflows?

Lower-level workflows are implementation details. They may ingest documents, retrieve chunks, build prompts, call generation, or validate citations, but they do not by themselves define the app integration contract. `VerifiedMemoryService` centralizes:

- supported operation names;
- audit metadata;
- `safe_to_show` decisions;
- validation severity reporting;
- request and response contract objects;
- future envelope wrapping for route/UI code.

Future app, UI, or API code should treat the service response as the boundary object. It should not bypass validation by calling generation workflows directly.

## Supported operations

`VerifiedMemoryService` currently exposes these supported operations:

1. `ingest_document` - Load local `.txt` or `.md` source material into verified-memory storage while preserving source chunks and references.
2. `extract_claims` - Create candidate claims from stored local evidence. Claims remain low-confidence/unverified unless later policy workflows support stronger verification.
3. `build_context` - Retrieve a deterministic evidence/context package for a question.
4. `build_prompt` - Build a prompt from the verified context package, including evidence/citation constraints.
5. `validate_answer` - Validate an answer against available context and citation constraints.
6. `generate_answer` - Build context, build the prompt, invoke the configured LLM path, validate the generated answer, and return service-level safety metadata.

## Required safety chain

Generated answers must follow this chain:

```text
local evidence -> context -> prompt -> generation -> validation -> safe_to_show
```

A generated answer is incomplete unless the response includes validation metadata and audit metadata proving validation ran. Future route/UI code should use the service contract helper `assert_safe_service_response` before returning generated-answer payloads.

## Generation config

Generation behavior is controlled with `VerifiedMemoryGenerationConfig`. The config carries model settings such as model name, endpoint URL, temperature, timeout, and whether network LLM calls are allowed.

`allow_network_llm` defaults false. This default protects local/private evidence from being sent to external model APIs accidentally. Network model use must be explicitly requested by configuration, and tests should not depend on real network calls.

```python
from verified_memory.config import VerifiedMemoryGenerationConfig
from verified_memory.contracts import VerifiedMemoryAnswerRequest
from verified_memory.service import VerifiedMemoryService

service = VerifiedMemoryService.from_db_path("verified_memory.sqlite3")

request = VerifiedMemoryAnswerRequest(
    question="What does the SOP say about Wi-Fi?",
    generation_config=VerifiedMemoryGenerationConfig(
        model="local-model",
        endpoint_url="http://localhost:11434",
        allow_network_llm=True,
    ),
)

response = await service.generate_answer(request)

if response.safe_to_show:
    print(response.answer)
else:
    print(response.validation)
```

Do not put endpoint secrets, API keys, client names, or confidential document text in examples or route logs.

## Testing with a fake LLM call

Tests should inject a fake `llm_call` instead of making a real LLM or network call. This keeps tests deterministic and proves validation is enforced after generation.

```python
from verified_memory.config import VerifiedMemoryGenerationConfig
from verified_memory.contracts import VerifiedMemoryAnswerRequest
from verified_memory.service import VerifiedMemoryService

service = VerifiedMemoryService.from_db_path("test.sqlite3")

async def fake_llm_call(messages, **kwargs):
    return "The SOP says to connect to Wi-Fi during OOBE. [doc_001:chunk:001]"

request = VerifiedMemoryAnswerRequest(
    question="What does the SOP say about Wi-Fi?",
    generation_config=VerifiedMemoryGenerationConfig(model="fake-test-model"),
)

response = await service.generate_answer(request, llm_call=fake_llm_call)
assert response.audit["answer_validated"] is True
```

## `safe_to_show`

`safe_to_show` means the service completed answer validation and determined the generated answer can be displayed to a user. It is not a claim that the answer is globally true; it means the answer satisfied the current deterministic validation checks, including citation/source constraints. If `safe_to_show` is false, callers should show validation details or a safe fallback instead of the generated answer.

## `validation_severity`

`validation_severity` summarizes the answer validation result. A passing severity means no blocking validation issue was found. An error severity means the answer must not be displayed as-is. Future UI/API code should avoid inventing its own severity interpretation and should rely on the service response.

## Audit metadata

Audit metadata records boundary-relevant facts such as operation name, whether an LLM was called, whether web behavior was called, whether generation config was validated, whether answer validation ran, validation severity, issue codes, and the final `safe_to_show` decision. This metadata is intended for debugging, policy review, tests, and future integration guardrails.

## Service envelopes for future integration

`VerifiedMemoryServiceEnvelope` is a side-effect-free dataclass wrapper for service responses. It does not call the database, does not call an LLM, and does not import route, search, research, ChromaDB, or legacy-memory modules.

```python
from verified_memory.contracts import VerifiedMemoryServiceEnvelope, assert_safe_service_response

payload = response.to_dict()
assert_safe_service_response(payload)

envelope = VerifiedMemoryServiceEnvelope.success(
    "generate_answer",
    payload,
    audit=payload["audit"],
)
json_ready = envelope.to_dict()
```

## Explicitly out of scope

This service boundary milestone does not add or integrate any of the following:

- web verification;
- search integration;
- UI routes or FastAPI routes;
- ChromaDB/vector memory integration;
- legacy memory mutation;
- nightly refresh;
- PDF/DOCX ingestion.

Existing Odysseus memory behavior, search/research routes, UI code, and ChromaDB behavior must remain unchanged by this milestone.
