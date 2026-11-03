"""One trusted browser-to-project identity mapping for project APIs."""

from fastapi import HTTPException, Request

from src.auth_helpers import require_user
from verified_memory.contracts.project_contract import RequestScope


def require_project_scope(request: Request, project_id: str) -> RequestScope:
    owner = require_user(request)
    try:
        return RequestScope(owner or '__local_operator__', project_id)
    except ValueError as exc:
        raise HTTPException(400, detail={'code': 'invalid_project', 'message': 'Invalid project ID'}) from exc
