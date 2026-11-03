import json

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import src.configured_local_models as configured
from core.database import Base, ModelEndpoint
from verified_memory.contracts.project_contract import RequestScope
from verified_memory.errors import RecordNotFoundError


@pytest.fixture()
def registry(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(configured, 'SessionLocal', factory)
    def add(id='local', **kwargs):
        values = {'name': id, 'base_url': 'http://localhost:11434/v1', 'is_enabled': True,
                  'owner': 'alice', 'cached_models': json.dumps(['chat-model']), 'model_type': 'llm'}
        values.update(kwargs)
        with factory() as db:
            db.add(ModelEndpoint(id=id, **values))
            db.commit()
    yield configured.ConfiguredLocalModels(), add
    engine.dispose()


@pytest.mark.parametrize('extra', [
    {'owner': 'bob'}, {'is_enabled': False}, {'base_url': 'https://api.example.com/v1'},
    {'base_url': 'http://192.168.1.2/v1'}, {'base_url': 'http://user:password@localhost/v1'},
    {'endpoint_kind': 'proxy'}, {'endpoint_kind': 'api'}, {'provider_auth_id': 'oauth-session'},
    {'model_type': 'image'}, {'hidden_models': '["chat-model"]'}, {'cached_models': 'broken-json'},
    {'cached_models': '["embedding-v3"]'},
])
def test_ineligible_endpoints_are_not_listed_or_resolved(registry, extra, monkeypatch):
    models, add = registry
    add(**extra)
    monkeypatch.setattr(configured, 'build_chat_url', lambda *_: pytest.fail('Ineligible endpoint reached resolver'))
    scope = RequestScope('alice', 'project')
    assert models.list_models(scope) == []
    with pytest.raises(RecordNotFoundError):
        models.resolve(scope, 'local', 'chat-model')


def test_shared_and_owned_models_are_selected_explicitly_without_exposing_secrets(registry, monkeypatch):
    models, add = registry
    add(api_key='fixture-secret', cached_models='["chat-model", "hidden", "chat-model", "whisper-1"]',
        pinned_models='["pinned-chat"]', hidden_models='["hidden"]')
    add('shared', owner=None)
    scope = RequestScope('alice', 'project')
    listed = models.list_models(scope)
    assert [(x['endpoint_id'], x['model']) for x in listed] == [('local', 'chat-model'), ('local', 'pinned-chat'), ('shared', 'chat-model')]
    assert 'fixture-secret' not in json.dumps(listed) and 'localhost' not in json.dumps(listed)
    monkeypatch.setattr(configured, 'build_chat_url', lambda base: base + '/chat/completions')
    adapter = models.resolve(scope, 'local', 'chat-model')
    assert adapter.url == 'http://localhost:11434/v1/chat/completions'
    assert adapter.headers['Authorization'] == 'Bearer fixture-secret'
    assert [x['endpoint_id'] for x in models.list_models(RequestScope('bob', 'project'))] == ['shared']
    with pytest.raises(RecordNotFoundError):
        models.resolve(scope, 'local', 'unlisted-model')


def test_listing_does_not_read_api_keys(registry):
    models, add = registry
    add(api_key='fixture-secret')
    engine = configured.SessionLocal.kw['bind']
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', record)
    try:
        assert models.list_models(RequestScope('alice', 'project'))
        assert statements and all('api_key' not in sql for sql in statements)
    finally:
        event.remove(engine, 'before_cursor_execute', record)
