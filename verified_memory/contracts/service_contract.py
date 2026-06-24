"""Side-effect-free service envelope and safety checks.

This module is intentionally limited to dataclasses and plain Python data. It
must not import storage, routes, search, ChromaDB, or LLM integration modules.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VerifiedMemoryServiceEnvelope:
    """JSON-friendly wrapper for app-facing verified-memory service results."""

    operation: str
    ok: bool
    payload: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    audit: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary without mutating the payload."""
        return {
            "operation": self.operation,
            "ok": self.ok,
            "payload": deepcopy(self.payload) if self.payload is not None else None,
            "error": deepcopy(self.error) if self.error is not None else None,
            "audit": deepcopy(self.audit),
            "metadata": deepcopy(self.metadata),
        }

    @classmethod
    def success(
        cls,
        operation: str,
        payload: dict[str, Any],
        *,
        audit: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "VerifiedMemoryServiceEnvelope":
        """Build a successful service envelope."""
        return cls(
            operation=operation,
            ok=True,
            payload=deepcopy(payload),
            error=None,
            audit=deepcopy(audit or {}),
            metadata=deepcopy(metadata or {}),
        )

    @classmethod
    def failure(
        cls,
        operation: str,
        error: dict[str, Any] | str,
        *,
        audit: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "VerifiedMemoryServiceEnvelope":
        """Build a failed service envelope."""
        error_payload = {"message": error} if isinstance(error, str) else deepcopy(error)
        return cls(
            operation=operation,
            ok=False,
            payload=None,
            error=error_payload,
            audit=deepcopy(audit or {}),
            metadata=deepcopy(metadata or {}),
        )


def assert_safe_service_response(payload: dict[str, Any]) -> None:
    """Validate that generated-answer payloads include return-safety metadata.

    Future route/UI code should call this before returning service payloads. The
    helper is deliberately strict for generated answers because an answer must
    not leave the service boundary unless deterministic validation metadata is
    present and confirms that validation ran.
    """
    operation = payload.get("operation")
    if operation != "generate_answer":
        return

    missing = []
    if "safe_to_show" not in payload:
        missing.append("safe_to_show")
    if "validation" not in payload and "validation_severity" not in payload:
        missing.append("validation or validation_severity")
    if "audit" not in payload:
        missing.append("audit")
    if missing:
        raise ValueError(f"Generated-answer service response missing required metadata: {', '.join(missing)}")

    audit = payload.get("audit")
    if not isinstance(audit, dict):
        raise ValueError("Generated-answer service response audit metadata must be a dictionary")
    if audit.get("answer_validated") is not True:
        raise ValueError("Generated-answer service response requires audit.answer_validated=true")
