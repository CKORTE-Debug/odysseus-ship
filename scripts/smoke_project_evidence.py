"""DOM smoke against real project APIs, with an injected local-model fixture.

Run with HAPPY_DOM_MODULE pointing to happy-dom's ESM entry if it is not
installed normally. Requires Node, happy-dom, beautifulsoup4 and uvicorn in the
development environment. No full-app startup or rendered browser is claimed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def serve(port: int):
    import uvicorn
    from bs4 import BeautifulSoup
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    from companion_core.application import ProjectCompanionService
    from companion_core.kernel import OdysseusLocalAdapter
    from routes.project_companion_routes import setup_project_companion_routes
    from routes.verified_memory_routes import setup_verified_memory_routes
    from verified_memory.service import VerifiedMemoryWorkspace

    counts = Counter()
    class FixtureModels:
        def list_models(self, scope):
            return [{'endpoint_id': 'fixture', 'model': 'fixture', 'label': 'Local protocol fixture'}]

        def resolve(self, scope, endpoint_id, model):
            if (endpoint_id, model) != ('fixture', 'fixture'):
                raise ValueError('Unknown fixture model')
            async def call(url, model, messages, **kwargs):
                context = json.loads(messages[1]['content'])
                task_id = kwargs['session_id']
                counts[task_id] += 1
                if context['evidence']['query']['question'] == 'cancel me' and counts[task_id] == 1:
                    await asyncio.sleep(30)
                return 'Use the evidence explorer. <img src=x onerror="window.modelExecuted=true"> [' + context['required_sources'][0]['revision_id'] + ']'
            return OdysseusLocalAdapter('http://localhost/v1/chat/completions', model, call=call)

    with tempfile.TemporaryDirectory() as directory:
        app = FastAPI()
        app.state.auth_manager = SimpleNamespace(is_configured=True)
        @app.middleware('http')
        async def identity(request, call_next):
            request.state.current_user = 'dom-fixture'
            return await call_next(request)
        memory = VerifiedMemoryWorkspace(Path(directory) / 'memory')
        app.include_router(setup_verified_memory_routes(memory))
        app.include_router(setup_project_companion_routes(ProjectCompanionService(memory, FixtureModels(), Path(directory) / 'tasks')))
        @app.get('/')
        async def index():
            soup = BeautifulSoup((ROOT / 'static/index.html').read_text(), 'html.parser')
            panel = soup.select_one('[data-memory-panel="evidence"]')
            panel['class'] = ['memory-tab-panel']
            return HTMLResponse('<!doctype html><html><body>' + str(panel) + '</body></html>')
        uvicorn.run(app, host='127.0.0.1', port=port, log_level='error')


def run():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    env = {**os.environ, 'DATABASE_URL': 'sqlite:///:memory:', 'AUTH_ENABLED': 'true'}
    server = subprocess.Popen([sys.executable, __file__, '--serve', '--port', str(port)], cwd=ROOT, env=env)
    try:
        origin = f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                with urllib.request.urlopen(origin, timeout=0.5):
                    break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('DOM fixture server stopped') from None
                time.sleep(0.05)
        else:
            raise RuntimeError('DOM fixture server did not start')
        subprocess.run(['node', str(ROOT / 'scripts/smoke_project_evidence.mjs'), origin], cwd=ROOT, env=env, check=True, timeout=45)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    serve(args.port) if args.serve else run()
