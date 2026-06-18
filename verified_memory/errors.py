"""Custom exceptions for verified memory."""


class VerifiedMemoryError(Exception):
    """Base exception for verified-memory failures."""


class InvalidRecordError(VerifiedMemoryError, ValueError):
    """Raised when a verified-memory model fails validation."""


class RecordNotFoundError(VerifiedMemoryError, LookupError):
    """Raised when a requested verified-memory record does not exist."""
