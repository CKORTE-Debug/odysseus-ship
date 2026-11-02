"""Exercise the existing llm_core HTTP path against a loopback protocol fixture.

This confirms integration and credentials, not real model inference or quality.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.configured_local_models as configured
from companion_core.application import ProjectCompanionService, ProjectTaskSpec
from core.database import Base, ModelEndpoint
from src import llm_core
from verified_memory.contracts.project_contract import (
    EvidenceQuery,
    RequestScope,
    SourceInput,
)
from verified_memory.service import VerifiedMemoryWorkspace


@pytest.mark.asyncio
async def test_configured_model_through_real_llm_http_client(tmp_path, monkeypatch):
    # The fixture talks directly to its own loopback socket; host proxy
    # configuration must not turn this into an external network request.
    for name in ('ALL_PROXY', 'all_proxy', 'HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_core, '_http_client', None)
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, self.headers.get('Authorization'), body))
            context = json.loads(body['messages'][1]['content'])
            revision = context['required_sources'][0]['revision_id']
            answer = 'Use the evidence explorer. [' + revision + ']'
            result = json.dumps({'choices': [{'message': {'role': 'assistant', 'content': answer}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(result)))
            self.end_headers()
            self.wfile.write(result)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(configured, 'SessionLocal', factory)
    with factory() as db:
        db.add(ModelEndpoint(id='wire', name='Wire fixture', base_url=f'http://127.0.0.1:{server.server_port}/v1',
                             is_enabled=True, api_key='fixture-key', owner='alice', cached_models='["wire-fixture"]'))
        db.commit()
    scope = RequestScope('alice', 'project')
    workspace = VerifiedMemoryWorkspace(tmp_path / 'memory')
    memory = workspace.create_project(scope)
    for role in ('procedure', 'current_state'):
        memory.register_source(SourceInput(f'{role}.md', 'Use the evidence explorer.', canonical_role=role,
                                           authority='canonical', owner_approved=True))
    service = ProjectCompanionService(workspace, configured.ConfiguredLocalModels(), tmp_path / 'companion')
    try:
        service.initialize(scope)
        service.start(scope, ProjectTaskSpec('wire-task', EvidenceQuery('evidence explorer'), 'wire', 'wire-fixture'))
        for _ in range(200):
            task = service.task(scope, 'wire-task')
            if not task['live']:
                break
            await asyncio.sleep(0.01)
        assert task['status'] == 'review_required', task
        assert len(requests) == 1
        assert requests[0][0:2] == ('/v1/chat/completions', 'Bearer fixture-key')
        assert requests[0][2]['model'] == 'wire-fixture'
        assert 'fixture-key' not in json.dumps(task)
    finally:
        await service.close()
        if llm_core._http_client is not None:
            await llm_core._http_client.aclose()
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=1)
        engine.dispose()
