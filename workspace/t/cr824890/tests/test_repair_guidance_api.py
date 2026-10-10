"""Offline HTTP/SQLite recovery contracts; no model, compiler or teacher claims."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from math_agent.domain import RepairGuidanceRequest
from math_agent.util import AgentError
from math_agent.web.app import create_app
from test_local_recovery import Provider, setup


@pytest.fixture
def blocked(tmp_path, monkeypatch):
    service, pipeline, plan, _ = setup(tmp_path, monkeypatch, Provider(fail_after=True))
    with pytest.raises(AgentError, match='repaired-candidate'):
        pipeline.lecture(plan)
    service.store.finish(pipeline.job, 'BLOCKED', 'review.section.S01', {'code': 'UNCERTAINTY_REVIEW_BLOCKED'})
    with service.store.transaction() as connection:
        connection.execute('UPDATE runs SET request_count=17 WHERE id=?', (pipeline.run['id'],))
    app = create_app(pipeline.settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.headers['X-CSRF-Token'] = client.get('/api/session').json()['csrf_token']
        yield service, pipeline, plan, client


def payload(blocked, **changes):
    service, pipeline, plan, client = blocked
    run = client.get('/api/runs/' + pipeline.run['id']).json()
    context = run['repair_guidance_context']
    assert context and context['section_id'] == 'S01'
    result = dict(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'],
                  action_id='bounded-suggestion', section_id='S01',
                  expected_candidate_hash=context['candidate_hash'], unit_ids=['S01.U1'],
                  instructions='补充定义适用的前提并逐项核实；该建议须经过通常数学审阅，不代替结论。', source='agent_audit')
    return {**result, **changes}


def events(service, run_id):
    with service.store.connect() as connection:
        return [json.loads(row[0]) for row in connection.execute(
            "SELECT payload_json FROM events WHERE run_id=? AND type='repair.guidance_requested'", (run_id,))]


def test_http_binds_saved_body_requeues_same_job_and_replays_lost_reply_once(blocked):
    service, pipeline, plan, client = blocked
    run_id = pipeline.run['id']; url = '/api/runs/' + run_id
    before = service.store.get_run(run_id)
    data = payload(blocked)
    first = client.post(url + '/repair-guidance', json=data)
    assert first.status_code == 202, first.text
    assert first.json()['id'] == pipeline.job['id'] and first.json()['status'] == 'queued'
    repeated = client.post(url + '/repair-guidance', json=data)
    assert repeated.status_code == 202 and repeated.json()['id'] == pipeline.job['id']
    after = client.get(url).json()
    assert after['status'] == 'QUEUED' and after['request_count'] == 17
    assert after['approval'] == before['approval'] and after['reviews'] == []
    assert len(after['jobs']) == len(before['jobs']) and after['repair_guidance_context'] is None
    saved = events(service, run_id)
    assert len(saved) == 1
    assert saved[0]['unit_ids'] == ['S01.U1'] and saved[0]['candidate_hash'] == data['expected_candidate_hash']
    assert saved[0]['recovery_binding']['state_sha256'] and saved[0]['candidate_file_hash']
    assert saved[0]['request_count_preserved'] == 17 and saved[0]['teacher_review'] == 'NOT_RUN'
    different = {**data, 'instructions': data['instructions'] + ' 此条为新建议。'}
    conflict = client.post(url + '/repair-guidance', json=different)
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'ACTION_CONFLICT'
    assert len(events(service, run_id)) == 1


@pytest.mark.parametrize('changes,code', [
    ({'expected_plan_revision': 999}, 'REVISION_CONFLICT'),
    ({'expected_plan_hash': '0' * 64}, 'REVISION_CONFLICT'),
    ({'expected_candidate_hash': '0' * 64}, 'GUIDANCE_CANDIDATE_CHANGED'),
    ({'unit_ids': ['S01.ABSENT']}, 'GUIDANCE_SCOPE_INVALID'),
    ({'section_id': 'S99'}, 'GUIDANCE_SCOPE_UNAVAILABLE'),
])
def test_wrong_plan_body_or_target_never_queues(blocked, changes, code):
    service, pipeline, _, client = blocked
    result = client.post('/api/runs/' + pipeline.run['id'] + '/repair-guidance', json=payload(blocked, **changes))
    assert result.status_code == 409 and result.json()['error']['code'] == code, result.text
    run = service.store.get_run(pipeline.run['id'])
    assert run['status'] == 'BLOCKED' and run['jobs'][0]['status'] == 'failed'
    assert not events(service, run['id'])


@pytest.mark.parametrize('changes', [
    {'instructions': ' ' * 20}, {'instructions': '太短'}, {'instructions': 'x' * 20001},
    {'unit_ids': []}, {'unit_ids': ['S01.U1', 'S01.U1']}, {'unit_ids': ['']},
    {'source': 'teacher_approved'}, {'skip_math_review': True},
])
def test_schema_rejects_ambiguous_or_approval_like_fields(blocked, changes):
    service, pipeline, _, client = blocked
    response = client.post('/api/runs/' + pipeline.run['id'] + '/repair-guidance', json=payload(blocked, **changes))
    assert response.status_code == 422
    assert not events(service, pipeline.run['id'])


@pytest.mark.parametrize('headers', [{'X-CSRF-Token': ''}, {'Origin': 'https://foreign.example'}])
def test_guidance_has_same_local_http_boundary(blocked, headers):
    service, pipeline, _, client = blocked
    response = client.post('/api/runs/' + pipeline.run['id'] + '/repair-guidance', json=payload(blocked), headers=headers)
    assert response.status_code == 403 and not events(service, pipeline.run['id'])


def test_budget_rejection_rolls_back_suggestion_event(blocked):
    service, pipeline, _, client = blocked
    data = payload(blocked)
    with service.store.transaction() as connection:
        connection.execute('UPDATE runs SET error_json=? WHERE id=?', (
            json.dumps({'code': 'BUDGET_EXHAUSTED', 'budget_version': 999}), pipeline.run['id']))
    response = client.post('/api/runs/' + pipeline.run['id'] + '/repair-guidance', json=data)
    assert response.status_code == 409 and response.json()['error']['code'] == 'BUDGET_EXHAUSTED'
    assert not events(service, pipeline.run['id'])
    assert service.store.get_run(pipeline.run['id'])['jobs'][0]['status'] == 'failed'


@pytest.mark.parametrize('change', ['approval', 'candidate', 'active', 'cancelled', 'workflow'])
def test_changed_persistent_preconditions_fail_without_mutation(blocked, change):
    service, pipeline, _, client = blocked
    data = payload(blocked); run_id = pipeline.run['id']
    if change == 'candidate':
        state = json.loads((pipeline.root / 'local-repair/S01.json').read_bytes())
        (pipeline.settings.workspace / state['candidate_key']).write_bytes(b'{}')
    else:
        with service.store.transaction() as connection:
            if change == 'approval':
                connection.execute('DELETE FROM approvals WHERE run_id=?', (run_id,))
            elif change == 'active':
                connection.execute("UPDATE jobs SET status='queued' WHERE id=?", (pipeline.job['id'],))
            elif change == 'cancelled':
                connection.execute("UPDATE runs SET status='CANCELLED' WHERE id=?", (run_id,))
            else:
                connection.execute("UPDATE runs SET workflow_id='slides.generate' WHERE id=?", (run_id,))
    response = client.post('/api/runs/' + run_id + '/repair-guidance', json=data)
    assert response.status_code == 409, response.text
    assert not events(service, run_id)


def test_background_benchmark_cannot_submit_explicit_suggestion(blocked):
    service, pipeline, _, _ = blocked
    request = RepairGuidanceRequest.model_validate(payload(blocked))
    service.actor = 'benchmark'
    with pytest.raises(AgentError) as error:
        service.request_repair_guidance(pipeline.run['id'], request)
    assert error.value.code == 'EXPLICIT_USER_GUIDANCE_REQUIRED'
    assert not events(service, pipeline.run['id'])
