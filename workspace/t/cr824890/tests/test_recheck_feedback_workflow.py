"""Unsupported Beamer feedback must not be silently accepted; offline API only."""
import json

import pytest
from fastapi.testclient import TestClient

from math_agent.domain import ConfirmRequest, ExecuteRequest, NewRun
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.web.app import create_app
from test_automatic_recheck_api import payload, publish_synthetic


pytestmark = pytest.mark.unit


@pytest.fixture
def beamer_case(tmp_path):
    settings = Settings(workspace=tmp_path/'w', reference_root=tmp_path/'refs')
    service = Service(settings)
    run = service.create(NewRun(workflow_id='beamer.from_tex', trusted_input=True))
    rid = run['id']
    with service.store.transaction() as connection:
        service.store.save_plan(connection, rid, {
            'title': 'Offline Beamer recheck fixture', 'provider': 'mock', 'theme': 'default',
            'sections': [], 'questions': [], 'unresolved_blocking_questions': [],
            'decisions': [], 'decision_ids': []})
    plan = service.store.get_run(rid)['plan']
    service.confirm(rid, ConfirmRequest(expected_plan_revision=plan['revision'],
        expected_plan_hash=plan['hash'], action_id='offline-beamer-confirmation'))
    service.execute(rid, ExecuteRequest(**payload(plan)))
    job = service.store.claim('offline-beamer-fixture')
    service.store.initialize_budget(job, {'requests': 60, 'local_repairs_per_unit': 2, 'global_repair_rounds': 2})
    publish_synthetic(service.store, settings, job, 'beamer-synthetic-delivery-not-compiled')
    service.store.finish(job, 'AWAITING_USER_REVIEW', 'review.pages_and_quality')
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['X-CSRF-Token'] = client.get('/api/session').json()['csrf_token']
        yield client, service, rid, plan


@pytest.mark.parametrize('source', ['user', 'agent_audit'])
def test_beamer_nonempty_feedback_is_rejected_without_archiving_or_enqueueing(beamer_case, source):
    client, service, rid, plan = beamer_case
    before = service.get(rid)
    response = client.post(f'/api/runs/{rid}/recheck', json={**payload(plan),
        'feedback': '请增加夹逼训练并修订原讲义数学内容。', 'feedback_source': source})
    assert response.status_code == 409, response.text
    assert response.json()['error']['code'] == 'RECHECK_FEEDBACK_UNSUPPORTED'
    assert service.get(rid) == before
    with service.store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM events WHERE run_id=? AND type='checks.rerun_requested'", (rid,)).fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM reviews WHERE run_id=?', (rid,)).fetchone()[0] == 0


def test_beamer_empty_feedback_retains_ordinary_idempotent_recheck(beamer_case):
    client, service, rid, plan = beamer_case
    before = service.get(rid)
    response = client.post(f'/api/runs/{rid}/recheck', json={**payload(plan), 'feedback': ''})
    assert response.status_code == 202, response.text
    replay = client.post(f'/api/runs/{rid}/recheck', json=payload(plan))
    assert replay.status_code == 202 and replay.json()['id'] == response.json()['id']
    after = service.get(rid)
    assert after['status'] == 'QUEUED'
    assert len(after['jobs']) == len(before['jobs']) + 1
    assert all(value['status'] == 'superseded' for value in after['artifacts'])
    for key in ('approval', 'plan', 'input', 'input_hash', 'request_count', 'reviews'):
        assert after[key] == before[key]
    assert after['budget'] == {**before['budget'], 'can_increase': False}
    with service.store.connect() as connection:
        values = [json.loads(row[0]) for row in connection.execute(
            "SELECT payload_json FROM events WHERE run_id=? AND type='checks.rerun_requested'", (rid,))]
    assert len(values) == 1 and values[0]['feedback'] == ''
    assert values[0]['teacher_review'] == 'NOT_PERFORMED'
