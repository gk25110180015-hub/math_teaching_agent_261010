"""Offline HTTP fixtures through real Service/SQLite/Worker; no vendor calls."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from math_agent.benchmark import request_metrics
from math_agent.domain import NewRun, LectureProposal
from math_agent.model_evidence import routing_summary
from math_agent.pipeline import Pipeline
from math_agent.provider import CompatibleChatProvider, MockProvider
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import canonical, digest
from math_agent.web.app import create_app
from math_agent.worker import Worker

pytestmark = pytest.mark.unit


def config(tmp_path, **updates):
    return Settings(workspace=tmp_path/'w', reference_root=tmp_path/'refs',
        live_api_enabled=True, api_key='synthetic-gpt-credential',
        deepseek_api_key='synthetic-deepseek-credential', llm_streaming=False,
        **updates)


def prepare(tmp_path, monkeypatch, statuses, *, model_id='gpt6', **updates):
    settings = config(tmp_path, **updates)
    service = Service(settings)
    calls = []
    proposal = MockProvider().generate('planner_lecture', {'topic':'Offline fixture'}, LectureProposal)

    def handler(request):
        body = json.loads(request.content)
        calls.append({'model': body['model'], 'host': request.url.host})
        status = statuses.get(body['model'], 200)
        return httpx.Response(status, json={'choices':[{'message':{'content':canonical(proposal)},
            'finish_reason':'stop'}], 'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})

    monkeypatch.setattr('math_agent.pipeline.CompatibleChatProvider',
        lambda *args, **kwargs: CompatibleChatProvider(*args, transport=httpx.MockTransport(handler), **kwargs))
    run = service.create(NewRun(workflow_id='lecture.generate', topic='Offline fixture',
        provider='live', model_id=model_id, trusted_input=True))
    service.propose(run['id'])
    worker = Worker(settings)
    assert worker.tick()
    return service, service.get(run['id']), calls


def events(service, run):
    with service.store.connect() as connection:
        return [dict(row) for row in connection.execute('SELECT * FROM events WHERE run_id=? ORDER BY sequence', (run['id'],))]


def test_504_routes_to_flash_without_losing_task_or_budget(tmp_path, monkeypatch):
    service, run, calls = prepare(tmp_path, monkeypatch, {'gpt-6-astra':504})
    assert [call['model'] for call in calls] == ['gpt-6-astra','deepseek-flash']
    assert run['status'] == 'AWAITING_PLAN_INPUT'
    assert run['request_count'] == 2 and run['input']['model_id'] == 'gpt6'
    assert run['plan']['model_id'] == 'gpt6'
    route = run['model_routing']
    assert route['fallback_count'] == 1 and route['last_successful_model_id'] == 'deepseek-flash'
    assert route['used_models'] == ['gpt6','deepseek-flash']
    metrics = request_metrics(events(service, run), run['request_count'], run['budget']['requests'])
    assert [record['status'] for record in metrics['requests']] == ['HTTP_504','SCHEMA_VALIDATED']
    assert [record['model_id'] for record in metrics['requests']] == ['gpt6','deepseek-flash']
    assert run['reviews'] == [] and run['approval'] is None


@pytest.mark.parametrize('model_id', ['gpt6','deepseek-flash','deepseek-v4-pro'])
def test_explicit_model_is_first_and_selection_survives_new_service(tmp_path, monkeypatch, model_id):
    service, run, calls = prepare(tmp_path, monkeypatch, {}, model_id=model_id)
    expected = 'gpt-6-astra' if model_id == 'gpt6' else model_id
    assert calls == [{'model':expected, 'host':'oneapi.advancedsolver.com' if model_id == 'gpt6' else 'api.deepseek.com'}]
    refreshed = Service(service.settings).get(run['id'])
    assert refreshed['input']['model_id'] == model_id and refreshed['plan']['model_id'] == model_id
    assert refreshed['model_routing']['last_successful_model_id'] == model_id
    assert refreshed['model_routing']['fallback_count'] == 0


def test_all_unavailable_preserves_diagnostic_and_count(tmp_path, monkeypatch):
    service, run, calls = prepare(tmp_path, monkeypatch, {'gpt-6-astra':504,'deepseek-flash':503,'deepseek-v4-pro':502})
    assert len(calls) == 3 and run['request_count'] == 3
    assert run['status'] == 'BLOCKED' and run['error']['code'] == 'PROVIDER_ALL_UNAVAILABLE'
    assert run['plan'] is None and run['reviews'] == []
    assert any(artifact['name'] == 'failure_diagnostic.json' for artifact in run['artifacts'])
    assert len(list((service.settings.workspace/'runs'/run['id']/'errors').glob('*.json'))) == 1
    assert run['model_routing']['last_successful_model_id'] is None


def test_fallback_does_not_bypass_persisted_request_budget(tmp_path, monkeypatch):
    service, run, calls = prepare(tmp_path, monkeypatch, {'gpt-6-astra':504}, max_requests_per_run=1)
    assert len(calls) == 1 and calls[0]['model'] == 'gpt-6-astra'
    assert run['request_count'] == 1 and run['status'] == 'BLOCKED'
    assert run['error']['code'] == 'BUDGET_EXHAUSTED'
    assert run['budget']['version'] == 0


def test_input_api_default_validation_and_no_credential_output(tmp_path):
    settings = config(tmp_path)
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['X-CSRF-Token'] = client.get('/api/session').json()['csrf_token']
        base = {'workflow_id':'lecture.generate','topic':'Offline API fixture'}
        created = client.post('/api/runs', json=base)
        assert created.status_code == 201 and created.json()['input']['model_id'] == 'gpt6'
        assert client.post('/api/runs', json={**base,'model_id':'unregistered'}).status_code == 422
        caps = client.get('/api/capabilities')
        assert [entry['id'] for entry in caps.json()['settings']['models']] == ['gpt6','deepseek-flash','deepseek-v4-pro']
        for response in (created, caps, client.get('/api/runs/'+created.json()['id'])):
            assert 'synthetic-gpt-credential' not in response.text
            assert 'synthetic-deepseek-credential' not in response.text


def test_legacy_model_default_is_read_only(tmp_path):
    service = Service(config(tmp_path))
    run = service.create(NewRun(workflow_id='lecture.generate',topic='Legacy fixture'))
    payload = dict(run['input']); payload.pop('model_id')
    with service.store.transaction() as connection:
        connection.execute('UPDATE runs SET input_json=?,input_hash=? WHERE id=?', (canonical(payload),digest(payload),run['id']))
        service.store.event(connection,run['id'],'provider.request',{'role':'planner_lecture','model':'gpt-6-astra'})
    before = service.store.get_run(run['id'])
    route = service.get(run['id'])['model_routing']
    assert route['preferred_model_id'] == 'gpt6' and route['selection_source'] == 'legacy_default'
    assert route['actual_models'] == ['gpt-6-astra'] and route['request_counts'] == {'gpt6':1}
    assert service.store.get_run(run['id']) == before


def test_routing_notifications_and_late_results_do_not_relabel_requests():
    event_list = [
        {'sequence':1,'type':'provider.request','payload':{'role':'writer','model_id':'gpt6','call_id':'a'}},
        {'sequence':2,'type':'provider.result','payload':{'role':'writer','call_id':'a','http_status':504}},
        {'sequence':3,'type':'provider.result','payload':{'role':'writer','event':'model_fallback','status':'FALLBACK'}},
        {'sequence':4,'type':'provider.request','payload':{'role':'writer','model_id':'deepseek-flash','call_id':'b'}},
        {'sequence':5,'type':'provider.result','payload':{'role':'writer','call_id':'a','http_status':504}},
        {'sequence':6,'type':'provider.result','payload':{'role':'writer','call_id':'b','output_hash':'validated'}},
    ]
    metrics = request_metrics(event_list,2,60)
    assert [item['status'] for item in metrics['requests']] == ['HTTP_504','SCHEMA_VALIDATED']
    assert metrics['requests'][1].get('http_status') is None


def test_export_manifest_identifies_preference_and_actual_fallback(tmp_path, monkeypatch):
    service, run, _ = prepare(tmp_path, monkeypatch, {'gpt-6-astra':504})
    # Export assembly only. Actual compiler tests run separately in the suite.
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.settings, pipeline.store, pipeline.run = service.settings, service.store, run
    pipeline.model_id = 'gpt6'
    source = tmp_path/'s'; source.mkdir(); (source/'lecture.tex').write_text('Fixture',encoding='utf-8')
    output = tmp_path/'o'; output.mkdir()
    pipeline.export_source(source,'lecture.tex',output,run['plan'])
    manifest = json.loads((output/'build_manifest.json').read_text(encoding='utf-8'))
    assert manifest['model_field_meaning'] == 'preferred_model_not_exclusive_authorship'
    assert manifest['model_routing']['successful_models'] == ['deepseek-flash']
    assert manifest['compiler']['status'] == 'NOT_RUN'
