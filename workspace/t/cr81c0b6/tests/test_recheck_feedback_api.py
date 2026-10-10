"""Offline feedback API: actual SQLite/session routing; no model/TeX/human review."""
import json

import pytest

from math_agent.domain import ExecuteRequest
from math_agent.util import canonical, digest
from test_automatic_recheck_api import case, payload, request_recheck


pytestmark = pytest.mark.unit


def events(service, run_id):
    with service.store.connect() as connection:
        return [dict(row) for row in connection.execute(
            'SELECT * FROM events WHERE run_id=? ORDER BY sequence', (run_id,))]


@pytest.mark.parametrize('source', ['user', 'agent_audit'])
def test_feedback_is_bound_to_approved_plan_and_does_not_sign_review_or_reset_budget(case, source):
    client, service, pipeline, plan = case
    rid = pipeline.run['id']
    before = service.get(rid)
    old_events = events(service, rid)
    feedback = '请补充夹逼训练、两个重要极限经典形式及抵消反例。\n保留已批准教学范围。'
    response = request_recheck(client, pipeline, plan, feedback=feedback, feedback_source=source)
    assert response.status_code == 202, response.text
    after = service.get(rid)
    for key in ('approval', 'plan', 'input', 'input_hash', 'request_count', 'reviews'):
        assert after[key] == before[key], key
    assert after['reviews'] == [] and after['request_count'] == 1
    assert after['budget'] == {**before['budget'], 'can_increase': False}
    assert all(value['status'] == 'superseded' for value in after['artifacts'])
    recorded = events(service, rid)
    added = recorded[len(old_events):]
    assert not any(value['type'] in ('human.review', 'plan.confirmed', 'budget.increased_by_user', 'provider.request') for value in added)
    rechecks = [json.loads(value['payload_json']) for value in added if value['type'] == 'checks.rerun_requested']
    assert len(rechecks) == 1
    event = rechecks[0]
    assert event['feedback'] == feedback and event['feedback_source'] == source
    assert event['plan_hash'] == before['approval']['hash'] == plan['hash']
    assert event['plan_revision'] == before['approval']['revision'] == plan['revision']
    assert event['job_id'] == response.json()['id']
    assert event['teacher_review'] == 'NOT_PERFORMED'
    assert event['payload_hash'] == digest({**payload(plan), 'feedback': feedback, 'feedback_source': source})


def test_missing_feedback_is_empty_user_feedback_and_replays_with_explicit_defaults(case):
    client, service, pipeline, plan = case
    first = request_recheck(client, pipeline, plan)
    assert first.status_code == 202
    replay = request_recheck(client, pipeline, plan, feedback='', feedback_source='user')
    assert replay.status_code == 202 and replay.json()['id'] == first.json()['id']
    rechecks = [json.loads(value['payload_json']) for value in events(service, pipeline.run['id'])
                if value['type'] == 'checks.rerun_requested']
    assert len(rechecks) == 1
    assert rechecks[0]['feedback'] == '' and rechecks[0]['feedback_source'] == 'user'


@pytest.mark.parametrize('changed', [{'feedback': '改为只检查抵消反例'}, {'feedback_source': 'agent_audit'}])
def test_same_key_cannot_be_reused_for_changed_feedback_or_provenance(case, changed):
    client, service, pipeline, plan = case
    values = {'feedback': '检查夹逼训练', 'feedback_source': 'user'}
    first = request_recheck(client, pipeline, plan, **values)
    assert first.status_code == 202
    before = service.get(pipeline.run['id'])
    event_before = events(service, pipeline.run['id'])
    replay = request_recheck(client, pipeline, plan, **{**values, **changed})
    assert replay.status_code == 409 and replay.json()['error']['code'] == 'ACTION_CONFLICT'
    assert service.get(pipeline.run['id']) == before
    assert events(service, pipeline.run['id']) == event_before


@pytest.mark.parametrize('feedback,expected_status', [('', 202), ('新增反馈不能复用旧键', 409)])
def test_pre_feedback_legacy_event_replay_is_compatible_only_when_feedback_remains_empty(case, feedback, expected_status):
    client, service, pipeline, plan = case
    first = request_recheck(client, pipeline, plan)
    assert first.status_code == 202
    # In this isolated DB only, emulate a previously persisted ExecuteRequest hash.
    with service.store.transaction() as connection:
        event = connection.execute("SELECT sequence,payload_json FROM events WHERE run_id=? AND type='checks.rerun_requested'",
                                   (pipeline.run['id'],)).fetchone()
        old = json.loads(event['payload_json'])
        old.pop('feedback', None)
        old.pop('feedback_source', None)
        old['payload_hash'] = digest(payload(plan))
        connection.execute('UPDATE events SET payload_json=? WHERE sequence=?', (canonical(old), event['sequence']))
    state_before = service.get(pipeline.run['id'])
    history_before = events(service, pipeline.run['id'])
    replay = request_recheck(client, pipeline, plan, feedback=feedback)
    assert replay.status_code == expected_status, replay.text
    if expected_status == 202:
        assert replay.json()['id'] == first.json()['id']
    else:
        assert replay.json()['error']['code'] == 'ACTION_CONFLICT'
    assert service.get(pipeline.run['id']) == state_before
    assert events(service, pipeline.run['id']) == history_before


def test_existing_execute_request_python_caller_keeps_empty_feedback_compatibility(case):
    _, service, pipeline, plan = case
    result = service.recheck(pipeline.run['id'], ExecuteRequest(**payload(plan)))
    values = [json.loads(value['payload_json']) for value in events(service, pipeline.run['id'])
              if value['type'] == 'checks.rerun_requested']
    assert len(values) == 1 and values[0]['job_id'] == result['id']
    assert values[0]['feedback'] == '' and values[0]['feedback_source'] == 'user'


@pytest.mark.parametrize('invalid', [
    {'feedback': '文' * 10001}, {'feedback': None}, {'feedback': 123},
    {'feedback_source': 'teacher_approved'}, {'feedback_source': None},
])
def test_invalid_feedback_is_rejected_before_any_persistent_change(case, invalid):
    client, service, pipeline, plan = case
    before = service.get(pipeline.run['id'])
    old_events = events(service, pipeline.run['id'])
    assert request_recheck(client, pipeline, plan, **invalid).status_code == 422
    assert service.get(pipeline.run['id']) == before
    assert events(service, pipeline.run['id']) == old_events


def test_feedback_exact_limit_is_accepted_without_truncation(case):
    client, service, pipeline, plan = case
    feedback = '数' * 10000
    assert request_recheck(client, pipeline, plan, feedback=feedback).status_code == 202
    value = next(json.loads(value['payload_json']) for value in events(service, pipeline.run['id'])
                 if value['type'] == 'checks.rerun_requested')
    assert value['feedback'] == feedback


def test_execute_endpoint_does_not_accept_new_recheck_only_fields(case):
    client, service, pipeline, plan = case
    before = service.get(pipeline.run['id'])
    response = client.post(f'/api/runs/{pipeline.run["id"]}/execute',
                           json={**payload(plan), 'feedback': '应仅用于复检', 'feedback_source': 'user'})
    assert response.status_code == 422
    assert service.get(pipeline.run['id']) == before


@pytest.mark.parametrize('fault', ['cancelled', 'active', 'unconfirmed'])
def test_feedback_does_not_bypass_recheck_state_job_or_approval_gates(case, fault):
    client, service, pipeline, plan = case
    with service.store.transaction() as connection:
        if fault == 'cancelled':
            connection.execute("UPDATE runs SET status='CANCELLED' WHERE id=?", (pipeline.run['id'],))
        elif fault == 'active':
            connection.execute("UPDATE jobs SET status='queued' WHERE id=?", (pipeline.job['id'],))
        else:
            connection.execute('DELETE FROM approvals WHERE run_id=?', (pipeline.run['id'],))
    before = service.get(pipeline.run['id'])
    old_events = events(service, pipeline.run['id'])
    response = request_recheck(client, pipeline, plan, feedback='请补训练', feedback_source='agent_audit')
    assert response.status_code == 409
    assert service.get(pipeline.run['id']) == before
    assert events(service, pipeline.run['id']) == old_events
