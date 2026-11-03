"""Service boundary for verified-memory integrations."""

from verified_memory.service.verified_memory_service import VerifiedMemoryService, VerifiedMemoryServiceError
from verified_memory.service.workspace import VerifiedMemoryWorkspace

__all__ = ["VerifiedMemoryService", "VerifiedMemoryServiceError", "VerifiedMemoryWorkspace"]
