"""Real memory/journal/kernel integration; provider responses are deterministic fixtures."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from companion_core.application import (
    CompanionBusyError,
    CompanionConflictError,
    ProjectCompanionService,
    ProjectTaskSpec,
)
from companion_core.kernel import OdysseusLocalAdapter
from routes.project_companion_routes import setup_project_companion_routes
from verified_memory.contracts.project_contract import (
    EvidenceQuery,
    RequestScope,
    SourceInput,
)
from verified_memory.errors import ContextNotReadyError, RecordNotFoundError
from verified_memory.service import VerifiedMemoryWorkspace


class FixtureModels:
    def __init__(self):
        self.calls = []
        self.behavior = None

    def list_models(self, scope):
        return [{'endpoint_id': 'local', 'model': 'fixture', 'label': 'Local fixture'}]

    def resolve(self, scope, endpoint_id, model):
        if (endpoint_id, model) != ('local', 'fixture'):
            raise RecordNotFoundError('Configured local model is unavailable for this account')

        async def call(url, model, messages, **kwargs):
            self.calls.append((scope, kwargs))
            if self.behavior:
                return await self.behavior(messages)
            context = json.loads(messages[1]['content'])
            source = context['required_sources'][0]
            return 'Use the evidence explorer. [' + source['revision_id'] + ']'

        return OdysseusLocalAdapter('http://localhost:11434/v1/chat/completions', model, call=call)


@pytest.fixture()
def setup(tmp_path):
    scope = RequestScope('alice', 'project')
    memory = VerifiedMemoryWorkspace(tmp_path / 'memory')
    project = memory.create_project(scope)
    for role in ('procedure', 'current_state'):
        project.register_source(SourceInput(f'{role}.md', f'Approved {role}: use the evidence explorer.',
                                            authority='canonical', canonical_role=role, owner_approved=True))
    models = FixtureModels()
    service = ProjectCompanionService(memory, models, tmp_path / 'companion')
    return SimpleNamespace(scope=scope, memory=memory, project=project, models=models, service=service)


def spec(task_id='step-1'):
    return ProjectTaskSpec(task_id, EvidenceQuery('evidence explorer'), 'local', 'fixture')


async def finished(setup, task_id='step-1'):
    for _ in range(100):
        task = setup.service.task(setup.scope, task_id)
        if not task['live']:
            return task
        await asyncio.sleep(0.005)
    raise AssertionError('Fixture project step did not complete')


def test_reads_require_explicit_journal_initialization(setup):
    assert setup.service.list_tasks(setup.scope) == {'ready': False, 'tasks': []}
    assert setup.service.models(setup.scope)
    assert not setup.service.root.exists()
    with pytest.raises(CompanionConflictError, match='Enable'):
        setup.service.start(setup.scope, spec())
    assert not setup.models.calls


@pytest.mark.asyncio
async def test_start_replay_review_and_durable_provenance(setup):
    setup.service.initialize(setup.scope)
    first = setup.service.start(setup.scope, spec())
    assert first['status'] == 'queued' and first['checkpoint_version'] == 1
    assert setup.service.start(setup.scope, spec()) == first
    with pytest.raises(CompanionConflictError, match='different request'):
        setup.service.start(setup.scope, replace(spec(), query=EvidenceQuery('changed question')))
    task = await finished(setup)
    assert task['status'] == 'review_required'
    assert task['task_spec'] == spec().payload()
    assert task['context_sources'][0]['revision_id'] in task['answer']
    assert task['claim_support'] == 'not_evaluated'
    assert len(setup.models.calls) == 1
    before = setup.project.list_sources(include_history=True)
    with pytest.raises(CompanionConflictError):
        setup.service.review(setup.scope, 'step-1', 1, 'acknowledged')
    reviewed = setup.service.review(setup.scope, 'step-1', task['checkpoint_version'], 'acknowledged')
    assert reviewed['status'] == 'reviewed'
    assert reviewed['review']['reviewed_by'] == 'alice'
    assert setup.project.list_sources(include_history=True) == before
    assert setup.service.start(setup.scope, spec())['status'] == 'reviewed'
    summary = setup.service.list_tasks(setup.scope)['tasks'][0]
    assert 'answer' not in summary and 'validation' not in summary
    await setup.service.close()
    restarted = ProjectCompanionService(setup.memory, setup.models, setup.service.root)
    assert restarted.task(setup.scope, 'step-1')['status'] == 'reviewed'
    await restarted.close()


@pytest.mark.asyncio
async def test_missing_approved_context_blocks_before_task_write_or_call(setup):
    scope = RequestScope('alice', 'empty')
    setup.memory.create_project(scope)
    setup.service.initialize(scope)
    with pytest.raises(ContextNotReadyError):
        setup.service.start(scope, spec())
    assert setup.service.list_tasks(scope)['tasks'] == []
    assert not setup.models.calls
    await setup.service.close()


@pytest.mark.asyncio
async def test_immediate_cancellation_can_resume_without_spending_an_attempt(setup):
    setup.service.initialize(setup.scope)
    first = setup.service.start(setup.scope, spec())
    paused = await setup.service.cancel(setup.scope, 'step-1', first['checkpoint_version'])
    assert paused['status'] == 'paused' and paused['attempt'] == 0 and not paused['live']
    assert not setup.models.calls
    setup.service.resume(setup.scope, 'step-1', paused['checkpoint_version'])
    assert (await finished(setup))['status'] == 'review_required'
    await setup.service.close()


@pytest.mark.asyncio
async def test_running_cancellation_and_retry_budget(setup):
    entered = asyncio.Event()
    async def blocked(_):
        entered.set()
        await asyncio.Event().wait()
    setup.models.behavior = blocked
    setup.service.initialize(setup.scope)
    setup.service.start(setup.scope, spec())
    await asyncio.wait_for(entered.wait(), 1)
    running = setup.service.task(setup.scope, 'step-1')
    paused = await setup.service.cancel(setup.scope, 'step-1', running['checkpoint_version'])
    assert paused['attempt'] == 1 and paused['status'] == 'paused'
    async def failure(_):
        raise RuntimeError('secret-provider-detail')
    setup.models.behavior = failure
    setup.service.resume(setup.scope, 'step-1', paused['checkpoint_version'])
    failed = await finished(setup)
    assert failed['status'] == 'failed' and failed['attempt'] == 2
    assert 'secret-provider-detail' not in json.dumps(failed)
    with pytest.raises(CompanionConflictError, match='budget exhausted'):
        setup.service.resume(setup.scope, 'step-1', failed['checkpoint_version'])
    await setup.service.close()


@pytest.mark.asyncio
async def test_recovery_uses_saved_request_after_restart(setup):
    setup.service.initialize(setup.scope)
    setup.service._journal().save(setup.scope, 'step-1', {
        'status': 'running', 'attempt': 1, 'task_spec': spec().payload(), 'error_type': 'Interrupted',
    }, expected_version=0)
    assert not setup.service.task(setup.scope, 'step-1')['live']
    setup.service.resume(setup.scope, 'step-1', 1)
    result = await finished(setup)
    assert result['attempt'] == 2 and result['status'] == 'review_required'
    assert 'error_type' not in result
    assert result['task_spec'] == spec().payload()
    await setup.service.close()


@pytest.mark.asyncio
async def test_queue_has_one_active_call_capacity_and_cancellable_waiting_tasks(setup):
    entered = asyncio.Event()
    async def blocked(_):
        entered.set()
        await asyncio.Event().wait()
    setup.models.behavior = blocked
    setup.service.initialize(setup.scope)
    for i in range(8):
        setup.service.start(setup.scope, spec(f'step-{i}'))
    await asyncio.wait_for(entered.wait(), 1)
    assert len(setup.models.calls) == 1
    with pytest.raises(CompanionBusyError):
        setup.service.start(setup.scope, spec('overflow'))
    queued = setup.service.task(setup.scope, 'step-7')
    assert queued['status'] == 'queued' and queued['attempt'] == 0
    await setup.service.cancel(setup.scope, 'step-7', queued['checkpoint_version'])
    await setup.service.close()
    assert not setup.service._handles
    assert len(setup.models.calls) == 1
    with pytest.raises(CompanionConflictError, match='shutting down'):
        setup.service.start(setup.scope, spec('closed'))


@pytest.mark.asyncio
async def test_source_update_during_call_fails_without_output(setup):
    async def changing(_):
        setup.project.register_source(SourceInput('new.md', 'Source changed while the model was running.'))
        return 'An obsolete answer'
    setup.models.behavior = changing
    setup.service.initialize(setup.scope)
    setup.service.start(setup.scope, spec())
    result = await finished(setup)
    assert result['status'] == 'failed' and 'answer' not in result
    await setup.service.close()


@pytest.mark.asyncio
async def test_scope_isolation_and_disabled_model_precede_checkpoint_write(setup):
    setup.service.initialize(setup.scope)
    for foreign in (RequestScope('bob', 'project'), RequestScope('alice', 'other')):
        setup.memory.create_project(foreign)
        assert not setup.service.list_tasks(foreign)['tasks']
        with pytest.raises(RecordNotFoundError):
            setup.service.task(foreign, 'step-1')
    with pytest.raises(RecordNotFoundError):
        setup.service.start(setup.scope, replace(spec(), endpoint_id='not-permitted'))
    assert not setup.service.list_tasks(setup.scope)['tasks']
    setup.service.start(setup.scope, spec())
    task = await finished(setup)
    assert setup.service.review(setup.scope, 'step-1', task['checkpoint_version'], 'rejected')['status'] == 'rejected'
    with pytest.raises(CompanionConflictError):
        setup.service.resume(setup.scope, 'step-1', task['checkpoint_version'] + 1)
    await setup.service.close()


@pytest.fixture()
def client(setup, monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    app = FastAPI()
    app.state.auth_manager = SimpleNamespace(is_configured=True)
    @app.middleware('http')
    async def identity(request, call_next):
        request.state.current_user = request.headers.get('x-test-owner')
        request.state.api_token = request.headers.get('x-test-token') == 'true'
        return await call_next(request)
    app.include_router(setup_project_companion_routes(setup.service))
    with TestClient(app) as result:
        yield result


PREFIX = '/api/project-companion/projects/project'
HEADERS = {'x-test-owner': 'alice'}
BODY = {'task_id': 'step-1', 'question': 'evidence explorer', 'endpoint_id': 'local', 'model': 'fixture'}


@pytest.mark.parametrize('method,path,body', [
    ('get', '/models', None), ('get', '/tasks', None), ('get', '/tasks/step-1', None),
    ('post', '/initialize', {}), ('post', '/tasks', BODY),
    ('post', '/tasks/step-1/cancel', {'expected_version': 1}),
    ('post', '/tasks/step-1/resume', {'expected_version': 1}),
    ('post', '/tasks/step-1/review', {'expected_version': 1, 'decision': 'acknowledged'}),
])
def test_every_route_rejects_unauthenticated_or_bearer_callers(client, method, path, body):
    kwargs = {'json': body} if body is not None else {}
    assert getattr(client, method)(PREFIX + path, **kwargs).status_code == 401
    assert getattr(client, method)(PREFIX + path, headers={**HEADERS, 'x-test-token': 'true'}, **kwargs).status_code == 403


@pytest.mark.parametrize('field,value', [('actor_id', 'bob'), ('db_path', '/private'), ('url', 'https://remote'), ('owner', 'bob')])
def test_start_rejects_untrusted_configuration(client, field, value):
    assert client.post(PREFIX + '/tasks', json={**BODY, field: value}, headers=HEADERS).status_code == 422


def test_routes_run_review_and_replay_without_inference_duplication(client, setup):
    import time
    assert client.get(PREFIX + '/tasks', headers=HEADERS).json()['payload']['ready'] is False
    assert client.post(PREFIX + '/initialize', json={}, headers=HEADERS).status_code == 200
    started = client.post(PREFIX + '/tasks', json=BODY, headers=HEADERS)
    assert started.status_code == 202
    for _ in range(100):
        task = client.get(PREFIX + '/tasks/step-1', headers=HEADERS).json()['payload']
        if not task['live']:
            break
        time.sleep(0.005)
    assert task['status'] == 'review_required'
    assert client.post(PREFIX + '/tasks', json=BODY, headers=HEADERS).status_code == 202
    assert len(setup.models.calls) == 1
    assert client.post(PREFIX + '/tasks/step-1/review', json={'expected_version': 1, 'decision': 'acknowledged'}, headers=HEADERS).status_code == 409
    reviewed = client.post(PREFIX + '/tasks/step-1/review', json={'expected_version': task['checkpoint_version'], 'decision': 'acknowledged'}, headers=HEADERS)
    assert reviewed.json()['payload']['status'] == 'reviewed'
    assert client.post(PREFIX + '/tasks/step-1/resume', json={'expected_version': 4, 'question': 'replace'}, headers=HEADERS).status_code == 422
    assert client.get(PREFIX + '/tasks/step-1', headers={'x-test-owner': 'bob'}).status_code == 404
    assert client.get(PREFIX.replace('/projects/project', '/projects/missing') + '/tasks', headers=HEADERS).status_code == 404
