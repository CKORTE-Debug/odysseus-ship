"""Shared helpers for verified-memory models."""

from __future__ import annotations

from dataclasses import is_dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Mapping

from verified_memory.errors import InvalidRecordError


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def parse_datetime(value: datetime | str | None, field_name: str) -> datetime | None:
    """Parse ISO datetimes while preserving timezone-aware UTC values."""

    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise InvalidRecordError(f"{field_name} must be an ISO datetime: {value!r}") from exc
    else:
        raise InvalidRecordError(f"{field_name} must be a datetime, ISO string, or None")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def datetime_to_json(value: datetime | None) -> str | None:
    """Serialize a datetime using UTC ISO 8601 with a Z suffix."""

    if value is None:
        return None
    parsed = parse_datetime(value, "datetime")
    return parsed.isoformat().replace("+00:00", "Z")


def require_non_empty(value: str | None, field_name: str) -> str:
    """Validate and normalize a required non-empty string."""

    if value is None or not str(value).strip():
        raise InvalidRecordError(f"{field_name} must not be empty")
    return str(value).strip()


def validate_allowed(value: str, allowed: set[str], field_name: str) -> str:
    """Validate an enum-like string value."""

    normalized = require_non_empty(value, field_name)
    if normalized not in allowed:
        raise InvalidRecordError(
            f"{field_name} must be one of {sorted(allowed)}; got {normalized!r}"
        )
    return normalized


def metadata_dict(value: Mapping[str, Any] | None, field_name: str = "metadata") -> dict[str, Any]:
    """Validate metadata without dropping unknown keys."""

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise InvalidRecordError(f"{field_name} must be a mapping")
    return dict(value)


def json_ready(value: Any) -> Any:
    """Convert dataclasses and datetimes to JSON-serializable structures."""

    if isinstance(value, datetime):
        return datetime_to_json(value)
    if is_dataclass(value):
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return {k: json_ready(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value
