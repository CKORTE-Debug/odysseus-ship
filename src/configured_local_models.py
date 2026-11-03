"""Bridge existing owner-scoped ModelEndpoint settings into the local gateway.

Listing never probes providers or refreshes OAuth. The initial project workflow
uses only explicit configured loopback models, with no cloud/fallback selection.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

from sqlalchemy.orm import defer

from companion_core.kernel import OdysseusLocalAdapter
from core.database import ModelEndpoint, SessionLocal
from src.endpoint_resolver import build_chat_url, build_headers
from verified_memory.contracts.project_contract import RequestScope
from verified_memory.errors import RecordNotFoundError


class ConfiguredLocalModels:
    @staticmethod
    def _eligible(endpoint) -> bool:
        try:
            parsed = urlparse(endpoint.base_url or '')
            return (
                parsed.scheme in {'http', 'https'}
                and parsed.hostname in {'localhost', '127.0.0.1', '::1'}
                and parsed.username is None and parsed.password is None
                and endpoint.endpoint_kind not in {'api', 'proxy'}
                and not endpoint.provider_auth_id
                and endpoint.model_type in {None, 'llm'}
            )
        except ValueError:
            return False

    @staticmethod
    def _models(endpoint) -> list[str]:
        def values(raw):
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                return [m for m in parsed if isinstance(m, str) and 0 < len(m) <= 256] if isinstance(parsed, list) else []
            except (TypeError, ValueError):
                return []
        hidden = set(values(endpoint.hidden_models))
        models = values(endpoint.cached_models) + values(endpoint.pinned_models)
        non_chat = ('embedding', 'rerank', 'tts-', 'whisper', 'dall-e', 'stable-diffusion', 'moderation', 'clip')
        return list(dict.fromkeys(m for m in models if m not in hidden and not any(x in m.lower() for x in non_chat)))

    def _endpoints(self, db, scope):
        # Shared/legacy endpoints follow the existing application ownership rule.
        # Even administrators cannot select another user's private endpoint here.
        return db.query(ModelEndpoint).options(defer(ModelEndpoint.api_key)).filter(
            ModelEndpoint.is_enabled == True,
            (ModelEndpoint.owner == scope.actor_id) | (ModelEndpoint.owner == None),
        )

    def list_models(self, scope: RequestScope) -> list[dict[str, str]]:
        with SessionLocal() as db:
            return [
                {'endpoint_id': ep.id, 'model': model, 'label': f'{ep.name} · {model}'}
                for ep in self._endpoints(db, scope).all() if self._eligible(ep)
                for model in self._models(ep)
            ]

    def resolve(self, scope: RequestScope, endpoint_id: str, model: str) -> OdysseusLocalAdapter:
        with SessionLocal() as db:
            ep = self._endpoints(db, scope).filter(ModelEndpoint.id == endpoint_id).first()
            if ep is None or not self._eligible(ep) or model not in self._models(ep):
                raise RecordNotFoundError('Configured local model is unavailable for this account')
            # OAuth/session-backed providers were rejected before reading secrets
            # or resolving runtime credentials. These functions do not probe.
            url = build_chat_url(ep.base_url)
            return OdysseusLocalAdapter(url, model, headers=build_headers(ep.api_key, ep.base_url))
