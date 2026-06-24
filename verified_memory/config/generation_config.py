"""Deterministic configuration for verified-memory answer generation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


_TRUE_VALUES = {"true", "1", "yes"}
_FALSE_VALUES = {"false", "0", "no", ""}


@dataclass(frozen=True)
class VerifiedMemoryGenerationConfig:
    """Explicit LLM generation settings for verified-memory answers."""

    model: str = ""
    endpoint_url: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    allow_network_llm: bool = False
    provider: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self, *, llm_call_provided: bool = False) -> "VerifiedMemoryGenerationConfig":
        """Validate config before any LLM import or call is attempted."""

        if not 0.0 <= float(self.temperature) <= 1.0:
            raise ValueError("verified-memory generation temperature must be between 0.0 and 1.0")
        if self.max_tokens is not None and int(self.max_tokens) <= 0:
            raise ValueError("verified-memory generation max_tokens must be a positive integer when provided")
        if self.timeout_seconds is not None and float(self.timeout_seconds) <= 0:
            raise ValueError("verified-memory generation timeout_seconds must be positive when provided")

        model = (self.model or "").strip()
        endpoint = (self.endpoint_url or "").strip()
        if llm_call_provided:
            if self.model is not None and self.model != model:
                raise ValueError("verified-memory generation model must not be blank")
            return self

        if not self.allow_network_llm:
            raise ValueError(
                "verified-memory generation requires an injected llm_call or allow_network_llm=true; "
                "real LLM calls are disabled by default"
            )
        if not model:
            raise ValueError("verified-memory generation model is required when allow_network_llm=true")
        if not endpoint:
            raise ValueError("verified-memory generation endpoint_url is required when allow_network_llm=true")
        return self

    def to_dict(self) -> dict[str, Any]:
        """Return a safe serializable representation with no expanded permissions."""

        return {
            "model": self.model,
            "endpoint_url": self.endpoint_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "allow_network_llm": self.allow_network_llm,
            "provider": self.provider,
            "metadata": dict(self.metadata),
            "permissions": {
                "web": False,
                "search": False,
                "research": False,
                "chromadb": False,
                "ui": False,
            },
        }

    @classmethod
    def from_env(cls) -> "VerifiedMemoryGenerationConfig":
        """Build config from VERIFIED_MEMORY_* environment variables."""

        return cls(
            model=os.getenv("VERIFIED_MEMORY_LLM_MODEL", ""),
            endpoint_url=os.getenv("VERIFIED_MEMORY_LLM_URL"),
            temperature=_parse_float_env("VERIFIED_MEMORY_LLM_TEMPERATURE", 0.0),
            max_tokens=_parse_optional_int_env("VERIFIED_MEMORY_LLM_MAX_TOKENS"),
            timeout_seconds=_parse_optional_float_env("VERIFIED_MEMORY_LLM_TIMEOUT_SECONDS"),
            allow_network_llm=_parse_bool_env("VERIFIED_MEMORY_ALLOW_NETWORK_LLM", False),
        )


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be one of true/false, 1/0, or yes/no")


def _parse_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else float(raw)


def _parse_optional_float_env(name: str) -> float | None:
    raw = os.getenv(name)
    return None if raw is None or raw == "" else float(raw)


def _parse_optional_int_env(name: str) -> int | None:
    raw = os.getenv(name)
    return None if raw is None or raw == "" else int(raw)
