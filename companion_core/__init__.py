"""In-process companion integration; no background workers start on import."""

from companion_core.checkpoints import SQLiteCheckpointStore
from companion_core.kernel import (
    CompanionKernel,
    LocalModelGateway,
    OdysseusLocalAdapter,
)

__all__ = ['CompanionKernel', 'LocalModelGateway', 'OdysseusLocalAdapter', 'SQLiteCheckpointStore']
