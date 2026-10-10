"""Offline execution-before-build budget configuration via the authenticated API."""
import json
import os

import pytest
from fastapi.testclient import TestClient

from math_agent.budget import BudgetConfiguration
from math_agent.domain import ConfirmRequest, ExecuteRequest, NewRun, RevisePlanRequest
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import AgentError
from math_agent.web.app import create_app

pytestmark = pytest.mark.unit


@pytest.fixture
def planned(tmp_path, monkeypatch):
    for name in tuple(os.environ):
        if name.startswith(('MATH_AGENT_', 'OPENAI_', 'DEEPSEEK_')):
            monkeypatch.delenv(name)
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')
    settings = Settings(workspace=tmp_path / 'w', reference_root=tmp_path / 'refs', max_requests_per_run=8)
    app = create_app(settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.headers['X-CSRF-Token'] = client.get('/api/session').json()['csrf_token']
        service = app.state.service
        rid = service.create(NewRun(workflow_id='lecture.generate', topic='Offline budget plan', trusted_input=True))['id']
        service.propose(rid)
        job = service.store.claim('offline-budget-configuration')
        service.store.initialize_budget(job, {'requests': 8, 'local_repairs_per_unit': 2, 'global_repair_rounds': 2})
        for _ in range(2):
            service.store.count_request(job, 8, {'fixture': 'OFFLINE_NO_API'})
        with service.store.transaction() as connection:
            service.store.save_plan(connection, rid, {'title': 'Budget plan', 'provider': 'mock',
                'sections': [{'id': 'S01', 'title': 'One'}], 'questions': [], 'unresolved_blocking_questions': []})
        service.store.finish(job, 'PLAN_READY', 'plan.ready')
        yield client, service, rid, job


def request(service, rid, **changes):
    run = service.store.get_run(rid)
    return {'expected_version': service.get_budget(rid)['version'],
            'expected_plan_revision': run['plan']['revision'], 'expected_plan_hash': run['plan']['hash'],
            'requests': 3, 'local_repairs_per_unit': 0, 'global_repair_rounds': 0,
            'action_id': 'configure-1', 'note': 'Explicit offline prebuild budget choice', **changes}


def confirm(service, rid):
    plan = service.store.get_run(rid)['plan']
    service.confirm(rid, ConfirmRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], action_id='confirm'))


@pytest.mark.parametrize('status', ['PLAN_READY', 'AWAITING_PLAN_INPUT', 'PLAN_CONFIRMED'])
def test_configuration_can_decrease_to_used_plus_one_and_zero_repairs_without_execution(planned, status):
    client, service, rid, _ = planned
    if status == 'PLAN_CONFIRMED':
        confirm(service, rid)
    elif status == 'AWAITING_PLAN_INPUT':
        with service.store.transaction() as connection:
            plan = service.store.current_plan(connection, service.store.row(connection, rid))
            plan['unresolved_blocking_questions'] = ['Q1']
            service.store.save_plan(connection, rid, plan)
    before = service.store.get_run(rid)
    assert before['status'] == status
    assert client.get(f'/api/runs/{rid}').json()['budget']['can_configure']
    response = client.post(f'/api/runs/{rid}/budget/configure', json=request(service, rid))
    assert response.status_code == 200
    assert {key: response.json()[key] for key in ('requests', 'local_repairs_per_unit', 'global_repair_rounds')} == {
        'requests': 3, 'local_repairs_per_unit': 0, 'global_repair_rounds': 0}
    assert response.json()['request_count'] == 2 and response.json()['version'] == 1
    assert service.store.get_run(rid) == before
    with service.store.connect() as connection:
        event = json.loads(connection.execute("SELECT payload_json FROM events WHERE run_id=? AND type='budget.configured_by_user'", (rid,)).fetchone()[0])
        assert event['actor'] == 'local_user' and event['approval_preserved']
        assert event['request_count_preserved'] == 2 and event['execution'] == 'NOT_STARTED'
        assert connection.execute("SELECT count(*) FROM jobs WHERE run_id=? AND kind='build'", (rid,)).fetchone()[0] == 0


def test_configuration_can_increase_then_decrease_and_survives_new_worker_defaults(planned):
    client, service, rid, _ = planned
    url = f'/api/runs/{rid}/budget/configure'
    assert client.post(url, json=request(service, rid, requests=12, local_repairs_per_unit=20, global_repair_rounds=20)).status_code == 200
    assert client.post(url, json=request(service, rid, action_id='configure-2')).status_code == 200
    confirm(service, rid)
    plan = service.store.get_run(rid)['plan']
    service.execute(rid, ExecuteRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], idempotency_key='build'))
    job = service.store.claim('offline-new-worker')
    service.store.initialize_budget(job, {'requests': 100, 'local_repairs_per_unit': 2, 'global_repair_rounds': 2})
    budget = service.get_budget(rid)
    assert budget['requests'] == 3 and budget['request_count'] == 2
    assert budget['local_repairs_per_unit'] == budget['global_repair_rounds'] == 0
    assert not budget['can_configure'] and not budget['can_increase']


def test_idempotent_action_replay_even_after_build_and_cross_operation_conflict(planned):
    client, service, rid, _ = planned
    payload = request(service, rid, local_repairs_per_unit=1, global_repair_rounds=1)
    url = f'/api/runs/{rid}/budget/configure'
    first = client.post(url, json=payload)
    assert first.status_code == 200 and client.post(url, json=payload).json() == first.json()
    assert client.post(url, json={**payload, 'requests': 4}).status_code == 409
    assert client.post(f'/api/runs/{rid}/budget', json=payload).json()['error']['code'] == 'ACTION_CONFLICT'
    confirm(service, rid)
    plan = service.store.get_run(rid)['plan']
    service.execute(rid, ExecuteRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], idempotency_key='build'))
    assert client.post(url, json=payload).json() == first.json()
    assert service.get_budget(rid)['version'] == 1
    with service.store.connect() as connection:
        assert connection.execute('SELECT count(*) FROM budget_actions WHERE run_id=?', (rid,)).fetchone()[0] == 1


@pytest.mark.parametrize('changes,code', [({'requests': 2}, 'BUDGET_ALREADY_USED'),
    ({'requests': 1}, 'BUDGET_ALREADY_USED'), ({'expected_version': 9}, 'BUDGET_CONFLICT'),
    ({'expected_plan_hash': 'stale'}, 'PLAN_CONFLICT'), ({'expected_plan_revision': 99}, 'PLAN_CONFLICT')])
def test_stale_or_consumed_budget_rejected_without_mutation(planned, changes, code):
    client, service, rid, _ = planned
    before = service.store.get_run(rid), service.get_budget(rid)
    response = client.post(f'/api/runs/{rid}/budget/configure', json=request(service, rid, **changes))
    assert response.status_code in (400, 409) and response.json()['error']['code'] == code
    assert (service.store.get_run(rid), service.get_budget(rid)) == before


def test_revised_plan_requires_new_binding_but_remains_configurable(planned):
    client, service, rid, _ = planned
    old = request(service, rid)
    service.revise(rid, RevisePlanRequest(expected_plan_revision=old['expected_plan_revision'], title='New plan'))
    assert client.post(f'/api/runs/{rid}/budget/configure', json=old).status_code == 409
    assert service.get_budget(rid)['can_configure']
    assert client.post(f'/api/runs/{rid}/budget/configure', json=request(service, rid)).status_code == 200


@pytest.mark.parametrize('changes', [{'requests': True}, {'requests': '3'}, {'requests': 1001},
    {'local_repairs_per_unit': -1}, {'local_repairs_per_unit': 21}, {'global_repair_rounds': 2.5},
    {'global_repair_rounds': 21}, {'expected_plan_revision': None}, {'expected_plan_hash': None},
    {'requests': None, 'local_repairs_per_unit': None, 'global_repair_rounds': None}, {'note': '   '}])
def test_configuration_values_are_strict_and_bounded(planned, changes):
    client, service, rid, _ = planned
    assert client.post(f'/api/runs/{rid}/budget/configure', json=request(service, rid, **changes)).status_code == 422
    assert service.get_budget(rid)['version'] == 0


@pytest.mark.parametrize('status', ['queued', 'running', 'done', 'failed', 'cancelled'])
def test_any_build_history_disables_configuration_even_if_status_returns_to_plan(planned, status):
    client, service, rid, _ = planned
    confirm(service, rid)
    plan = service.store.get_run(rid)['plan']
    job = service.execute(rid, ExecuteRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], idempotency_key='build'))
    with service.store.transaction() as connection:
        connection.execute('UPDATE jobs SET status=? WHERE id=?', (status, job['id']))
        connection.execute("UPDATE runs SET status='PLAN_READY' WHERE id=?", (rid,))
    assert not service.get_budget(rid)['can_configure']
    response = client.post(f'/api/runs/{rid}/budget/configure', json=request(service, rid))
    assert response.status_code == 409
    assert response.json()['error']['code'] == ('BUDGET_JOB_ACTIVE' if status in ('queued', 'running') else 'BUDGET_BUILD_EXISTS')


def test_active_plan_job_and_unauthorized_actor_cannot_configure(planned):
    client, service, rid, job = planned
    other = Service(service.settings, actor='benchmark_driver')
    assert not other.get_budget(rid)['can_configure']
    with pytest.raises(AgentError) as error:
        other.configure_budget(rid, BudgetConfiguration.model_validate(request(service, rid)))
    assert error.value.code == 'EXPLICIT_USER_BUDGET_REQUIRED'
    with service.store.transaction() as connection:
        connection.execute("UPDATE jobs SET status='running' WHERE id=?", (job['id'],))
    assert not service.get_budget(rid)['can_configure']
    assert client.post(f'/api/runs/{rid}/budget/configure', json=request(service, rid)).json()['error']['code'] == 'BUDGET_JOB_ACTIVE'


def test_configuration_requires_plan_and_session_csrf_same_origin(planned):
    client, service, rid, _ = planned
    url = f'/api/runs/{rid}/budget/configure'
    payload = request(service, rid)
    assert client.post(url, json=payload, headers={'X-CSRF-Token': ''}).status_code == 403
    assert client.post(url, json=payload, headers={'Origin': 'https://foreign.example'}).status_code == 403
    empty = service.create(NewRun(workflow_id='lecture.generate', topic='No plan'))['id']
    assert not service.get_budget(empty)['can_configure']
    assert client.post(f'/api/runs/{empty}/budget/configure', json=payload).status_code == 409
    client.cookies.clear()
    assert client.post(url, json=payload).status_code == 403


def test_unknown_historical_baseline_still_requires_explicit_request_limit_confirmation(planned):
    client, service, rid, _ = planned
    with service.store.transaction() as connection:
        connection.execute('DELETE FROM run_budgets WHERE run_id=?', (rid,))
    url = f'/api/runs/{rid}/budget/configure'
    assert not service.get_budget(rid)['can_configure']
    assert client.post(url, json=request(service, rid)).json()['error']['code'] == 'BUDGET_BASELINE_UNKNOWN'
    response = client.post(url, json=request(service, rid, confirm_unknown_request_limit=True))
    assert response.status_code == 200 and response.json()['request_count'] == 2
    assert response.json()['requests'] == 3 and not response.json()['baseline_unknown']


def test_configuration_rolls_back_budget_and_action_if_audit_fails(planned, monkeypatch):
    _, service, rid, _ = planned
    before = service.get_budget(rid)
    event = service.store.event

    def fail_audit(connection, run_id, kind, payload=None):
        if kind == 'budget.configured_by_user':
            raise RuntimeError('Injected audit failure')
        return event(connection, run_id, kind, payload)

    monkeypatch.setattr(service.store, 'event', fail_audit)
    with pytest.raises(RuntimeError, match='audit failure'):
        service.configure_budget(rid, BudgetConfiguration.model_validate(request(service, rid)))
    assert service.get_budget(rid) == before
    with service.store.connect() as connection:
        assert connection.execute('SELECT count(*) FROM budget_actions WHERE run_id=?', (rid,)).fetchone()[0] == 0
