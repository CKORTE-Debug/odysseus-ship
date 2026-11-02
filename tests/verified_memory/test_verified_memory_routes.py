"""Integration tests for authenticated, scoped v2 memory routes.

Identity middleware below supplies the same trusted state as app.AuthMiddleware;
the real require_user/require_admin checks and SQLite services run unmocked.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.verified_memory_routes import setup_verified_memory_routes
from verified_memory.service import VerifiedMemoryWorkspace


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    app = FastAPI()
    app.state.auth_manager = SimpleNamespace(is_configured=True, is_admin=lambda owner: owner == 'admin')

    @app.middleware('http')
    async def identity(request, call_next):
        if request.headers.get('x-test-owner'):
            request.state.current_user = request.headers['x-test-owner']
        request.state.api_token = request.headers.get('x-test-api-token') == 'true'
        return await call_next(request)

    app.include_router(setup_verified_memory_routes(VerifiedMemoryWorkspace(tmp_path / 'memory')))
    with TestClient(app) as result:
        yield result


def headers(owner='alice'):
    return {'x-test-owner': owner}


def create(client, project='project', owner='alice'):
    response = client.post('/api/verified-memory/projects', json={'project_id': project}, headers=headers(owner))
    assert response.status_code == 200
    return response


def upload(client, text='Evidence explorer is the first milestone.', **extra):
    body = {'filename': 'plan.md', 'text': text, **extra}
    response = client.post('/api/verified-memory/projects/project/sources', json=body, headers=headers())
    assert response.status_code == 200, response.text
    return response.json()['payload']


def query(client, **extra):
    return client.post('/api/verified-memory/projects/project/query',
                       json={'question': 'evidence explorer', **extra}, headers=headers())


def test_health_reports_capabilities_without_promising_factual_verification(client):
    body = client.get('/api/verified-memory/health').json()
    assert body['contract_version'] == '1.0'
    assert body['capabilities']['project_sources']
    assert not body['capabilities']['generate_answer']
    assert not body['capabilities']['claim_support_verification']


@pytest.mark.parametrize('method,path,body', [
    ('post', '/api/verified-memory/projects', {'project_id': 'project'}),
    ('get', '/api/verified-memory/projects/project/sources', None),
    ('post', '/api/verified-memory/projects/project/query', {'question': 'test'}),
    ('post', '/api/verified-memory/context', {'question': 'test'}),
])
def test_private_routes_require_authentication(client, method, path, body):
    response = getattr(client, method)(path, **({'json': body} if body else {}))
    assert response.status_code == 401


def test_bearer_tokens_cannot_bypass_future_adapter_scopes(client):
    response = client.post('/api/verified-memory/projects', json={'project_id': 'project'},
                           headers={**headers(), 'x-test-api-token': 'true'})
    assert response.status_code == 403


def test_querying_missing_project_never_creates_storage(client, tmp_path):
    assert query(client).status_code == 404
    assert not (tmp_path / 'memory').exists()


def test_non_admin_can_import_into_their_own_project(client):
    create(client)
    source = upload(client)
    body = query(client).json()['payload']
    assert body['scope'] == {'actor_id': 'alice', 'project_id': 'project'}
    assert body['passages'][0]['source']['revision_id'] == source['revision_id']
    assert body['passages'][0]['claim_support'] == 'not_evaluated'
    assert body['remote_calls'] is False


@pytest.mark.parametrize('field,value', [
    ('db_path', '/etc/private.sqlite3'), ('owner_id', 'bob'), ('actor_id', 'bob'),
])
def test_query_rejects_client_storage_and_identity_fields(client, field, value):
    create(client)
    assert query(client, **{field: value}).status_code == 422


@pytest.mark.parametrize('field,value', [('db_path', 'other.db'), ('path', '/etc/private.md'), ('actor_id', 'bob')])
def test_upload_rejects_server_path_and_identity_fields(client, field, value):
    create(client)
    response = client.post('/api/verified-memory/projects/project/sources',
                           json={'filename': 'plan.md', 'text': 'text', field: value}, headers=headers())
    assert response.status_code == 422


@pytest.mark.parametrize('filename', [
    '../secret.md', '/etc/secret.md', r'C:\Users\Chris\secret.md',
    r'\\server\share\secret.md', 'secret.pdf', 'secret.md\x00.txt',
])
def test_import_only_accepts_uploaded_text_with_a_safe_name(client, filename):
    create(client)
    response = client.post('/api/verified-memory/projects/project/sources',
                           json={'filename': filename, 'text': 'not a path import'}, headers=headers())
    assert response.status_code == 400
    assert response.json()['detail']['error']['code'] == 'invalid_request'


def test_sources_are_isolated_between_owners_and_projects(client):
    create(client)
    source = upload(client, 'private evidence explorer secret')
    create(client, owner='bob')
    create(client, project='other')
    for project, owner in [('project', 'bob'), ('other', 'alice')]:
        response = client.get(f'/api/verified-memory/projects/{project}/sources/{source["revision_id"]}', headers=headers(owner))
        assert response.status_code == 404


def test_current_query_and_legacy_prompt_exclude_superseded_revision(client):
    create(client)
    old = upload(client, 'evidence explorer uses automatic deployment', effective_from='2026-01-01T00:00:00Z')
    new = upload(client, 'evidence explorer excludes automatic deployment', effective_from='2026-02-01T00:00:00Z')
    body = query(client).json()['payload']
    assert {p['source']['revision_id'] for p in body['passages']} == {new['revision_id']}
    historical = query(client, as_of='2026-01-15T00:00:00Z').json()['payload']
    assert historical['passages'][0]['source']['revision_id'] == old['revision_id']
    prompt = client.post('/api/verified-memory/prompt',
                         json={'project_id': 'project', 'question': 'evidence explorer'}, headers=headers()).json()['payload']
    assert 'excludes automatic deployment' in prompt['user_message']
    assert 'uses automatic deployment' not in prompt['user_message']


def test_exact_source_can_be_inspected_and_repeat_import_is_idempotent(client):
    create(client)
    original = '# Plan\n  exact indentation\n'
    first = upload(client, original)
    second = upload(client, original)
    assert second['revision_id'] == first['revision_id']
    response = client.get(f'/api/verified-memory/projects/project/sources/{first["revision_id"]}', headers=headers())
    assert response.json()['payload']['text'] == original
    sources = client.get('/api/verified-memory/projects/project/sources?include_history=true', headers=headers()).json()
    assert len(sources['payload']['sources']) == 1


def test_preflight_requires_explicit_approved_procedure_and_current_state(client):
    create(client)
    request = {'question': 'evidence explorer'}
    path = '/api/verified-memory/projects/project/prepare-context'
    assert client.post(path, json=request, headers=headers()).status_code == 409
    for role in ('procedure', 'current_state'):
        upload(client, 'evidence explorer project record', filename=f'{role}.md',
               authority='canonical', canonical_role=role, owner_approved=True)
    response = client.post(path, json=request, headers=headers())
    assert response.status_code == 200
    body = response.json()['payload']
    assert len(body['required_sources']) == 2
    assert body['live_upstream_revision_checked'] is False
    assert body['freshness'] == 'local_import_age_checked'


def test_preflight_rejects_expected_revision_mismatch(client):
    create(client)
    upload(client)
    response = client.post('/api/verified-memory/projects/project/prepare-context',
                           json={'question': 'plan', 'expected_revisions': {'plan.md': 'wrong'}}, headers=headers())
    assert response.status_code == 409


@pytest.mark.parametrize('path', ['/admin/ingest', '/admin/extract-claims'])
def test_retired_admin_operations_require_actual_admin_and_never_read_paths(client, path):
    endpoint = '/api/verified-memory' + path
    assert client.post(endpoint, json={'db_path': '/tmp/other.db'}, headers=headers()).status_code == 403
    assert client.post(endpoint, json={'db_path': '/tmp/other.db'}, headers=headers('admin')).status_code == 410


@pytest.mark.parametrize('payload', [
    {'question': 'test', 'limit': 0}, {'question': 'test', 'limit': 21},
    {'question': 'test', 'context_budget_chars': 100_000}, {'question': 'x' * 4001},
])
def test_work_budgets_are_bounded_at_api_boundary(client, payload):
    response = client.post('/api/verified-memory/projects/project/query', json=payload, headers=headers())
    assert response.status_code == 422


def test_validation_exposes_its_limited_scope(client):
    create(client)
    upload(client)
    response = client.post('/api/verified-memory/validate-answer', json={
        'project_id': 'project', 'question': 'evidence explorer',
        'answer': 'Unrelated factual claim. [invented]',
    }, headers=headers()).json()['payload']
    assert response['validation']['metadata']['claim_support'] == 'not_evaluated'
    assert response['validation']['metadata']['validation_scope'] == 'citation_and_heuristics'
    assert response['safe_to_show'] is False
