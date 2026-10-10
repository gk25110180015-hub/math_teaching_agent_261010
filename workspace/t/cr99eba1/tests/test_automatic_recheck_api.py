"""Offline automatic-recheck API: synthetic artifacts, actual SQLite and Worker."""
import json

import pytest
from fastapi.testclient import TestClient

from math_agent.pipeline import Pipeline
from math_agent.util import canonical, digest, now, uid, write_json
from math_agent.web.app import create_app
from math_agent.worker import Worker
from test_draft_recovery import OfflineProvider, setup_pipeline


pytestmark = pytest.mark.unit


def publish_synthetic(store, settings, job, label):
    folder = settings.workspace / 'runs' / job['run_id'] / label
    folder.mkdir(parents=True)
    values = [('page-001.png', 'image/png', b'OFFLINE_SYNTHETIC_IMAGE_NOT_RENDERED', {'physical_page': 1}),
              ('quality_report.json', 'application/json', b'{"fixture":"OFFLINE_NOT_TEACHER_ACCEPTED"}', {}),
              ('lecture.pdf', 'application/pdf', b'%PDF-1.4 OFFLINE_NOT_COMPILED', {})]
    artifacts = []
    for name, media, data, metadata in values:
        path = folder / name
        path.write_bytes(data)
        artifacts.append({'storage_key': path.relative_to(settings.workspace).as_posix(),
                          'name': name, 'media_type': media, 'sha256': digest(data), 'metadata': metadata})
    store.publish_artifacts(job, artifacts)


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setenv('MATH_AGENT_API_KEY', '')
    monkeypatch.setenv('MATH_AGENT_DEEPSEEK_API_KEY', '')
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')
    service, pipeline, plan = setup_pipeline(tmp_path, OfflineProvider(), max_requests_per_run=60)
    service.store.count_request(pipeline.job, 60, {'fixture': 'OFFLINE_NO_MODEL_REQUEST'})
    service.store.checkpoint(pipeline.job, 'section.S01', 'fixture-contract-v1',
                             {'fixture': 'CHECKPOINT_RETAINED_FOR_PIPELINE_CONTRACT_VALIDATION'})
    publish_synthetic(service.store, pipeline.settings, pipeline.job, 'initial-synthetic-delivery')
    service.store.finish(pipeline.job, 'AWAITING_USER_REVIEW', 'review.pages_and_quality')
    with TestClient(create_app(pipeline.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['X-CSRF-Token'] = client.get('/api/session').json()['csrf_token']
        yield client, service, pipeline, plan


def payload(plan, key='offline-user-recheck-1'):
    return {'expected_plan_revision': plan['revision'], 'expected_plan_hash': plan['hash'],
            'idempotency_key': key}


def request_recheck(client, pipeline, plan, **changes):
    return client.post(f'/api/runs/{pipeline.run["id"]}/recheck', json={**payload(plan), **changes})


def test_recheck_is_idempotent_and_preserves_approval_budget_checkpoints_and_history(case):
    client, service, pipeline, plan = case
    rid = pipeline.run['id']
    before = service.get(rid)
    response = request_recheck(client, pipeline, plan)
    assert response.status_code == 202, response.text
    job = response.json()
    assert job['kind'] == 'build' and job['status'] == 'queued' and job['id'] != pipeline.job['id']
    replay = request_recheck(client, pipeline, plan)
    assert replay.status_code == 202 and replay.json()['id'] == job['id']
    after = service.get(rid)
    assert after['status'] == 'QUEUED'
    assert after['approval'] == before['approval'] and after['input_hash'] == before['input_hash']
    assert after['request_count'] == before['request_count'] == 1
    assert after['budget'] == {**before['budget'], 'can_increase': False}
    assert after['reviews'] == before['reviews'] == []
    assert {a['artifact_id'] for a in after['artifacts']} == {a['artifact_id'] for a in before['artifacts']}
    assert all(a['status'] == 'superseded' for a in after['artifacts'])
    for artifact in after['artifacts']:
        download = client.get('/api/artifacts/' + artifact['artifact_id'])
        assert download.status_code == 200 and digest(download.content) == artifact['sha256']
    with service.store.connect() as connection:
        assert connection.execute('SELECT count(*) FROM steps WHERE run_id=?', (rid,)).fetchone()[0] == 1
        events = [dict(row) for row in connection.execute('SELECT * FROM events WHERE run_id=?', (rid,))]
    rechecks = [json.loads(row['payload_json']) for row in events if row['type'] == 'checks.rerun_requested']
    assert len(rechecks) == 1 and rechecks[0]['job_id'] == job['id']
    assert rechecks[0]['request_count_preserved'] == 1
    assert not any(row['type'] == 'human.review' for row in events)


def test_recheck_key_reuse_with_different_payload_is_conflict(case):
    client, _, pipeline, plan = case
    assert request_recheck(client, pipeline, plan).status_code == 202
    response = request_recheck(client, pipeline, plan, expected_plan_hash='different-plan')
    assert response.status_code == 409 and response.json()['error']['code'] == 'ACTION_CONFLICT'


@pytest.mark.parametrize('status', ['CANCELLED', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'PLAN_READY', 'BUILDING'])
def test_recheck_rejects_ineligible_task_states_without_archiving(case, status):
    client, service, pipeline, plan = case
    with service.store.transaction() as connection:
        connection.execute('UPDATE runs SET status=? WHERE id=?', (status, pipeline.run['id']))
    before = service.store.get_run(pipeline.run['id'])
    assert request_recheck(client, pipeline, plan).status_code == 409
    assert service.store.get_run(pipeline.run['id']) == before


@pytest.mark.parametrize('fault', ['stale_hash', 'stale_revision', 'unconfirmed', 'active_job'])
def test_recheck_checks_plan_approval_and_active_job_before_mutation(case, fault):
    client, service, pipeline, plan = case
    changes = {}
    if fault == 'stale_hash': changes['expected_plan_hash'] = 'stale'
    elif fault == 'stale_revision': changes['expected_plan_revision'] = 99
    else:
        with service.store.transaction() as connection:
            if fault == 'unconfirmed':
                connection.execute('DELETE FROM approvals WHERE run_id=?', (pipeline.run['id'],))
            else:
                connection.execute("INSERT INTO jobs(id,run_id,kind,build_key,status,created_at) VALUES(?,?,?,?,?,?)",
                                   (uid(), pipeline.run['id'], 'build', uid(), 'queued', now()))
    before = service.store.get_run(pipeline.run['id'])
    assert request_recheck(client, pipeline, plan, **changes).status_code == 409
    assert service.store.get_run(pipeline.run['id']) == before


def test_recheck_does_not_bypass_session_and_csrf(case):
    client, _, pipeline, plan = case
    response = client.post(f'/api/runs/{pipeline.run["id"]}/recheck', json=payload(plan),
                           headers={'X-CSRF-Token': ''})
    assert response.status_code == 403


def test_worker_rebuild_and_review_exclude_superseded_artifacts_and_old_issues(case, monkeypatch):
    client, service, pipeline, plan = case
    rid = pipeline.run['id']
    old = service.store.get_run(rid)['artifacts']
    old_page = next(a for a in old if a['media_type'] == 'image/png')
    review_url = f'/api/runs/{rid}/reviews'
    assert client.post(review_url, json={'artifact_id': old_page['artifact_id'], 'sha256': old_page['sha256'],
                                        'verdict': 'issue', 'note': 'OFFLINE historical issue fixture'}).status_code == 200
    assert request_recheck(client, pipeline, plan).status_code == 202
    observed = []
    def synthetic_build(self):
        observed.append(self.run['approval']['hash'])
        publish_synthetic(self.store, self.settings, self.job, 'rechecked-synthetic-delivery')
        self.store.finish(self.job, 'AWAITING_USER_REVIEW', 'review.pages_and_quality')
    monkeypatch.setattr(Pipeline, 'build', synthetic_build)
    assert Worker(pipeline.settings).tick()
    assert observed == [plan['hash']]
    current = service.store.get_run(rid)
    assert current['status'] == 'AWAITING_USER_REVIEW'
    assert len(current['reviews']) == 1  # The automatic action did not submit a human review.
    old_response = client.post(review_url, json={'artifact_id': old_page['artifact_id'],
        'sha256': old_page['sha256'], 'verdict': 'pass', 'note': 'Must remain rejected'})
    assert old_response.status_code == 409 and old_response.json()['error']['code'] == 'ARTIFACT_SUPERSEDED'
    fresh = [a for a in current['artifacts'] if a['status'] != 'superseded']
    for artifact in fresh:
        if artifact['media_type'] == 'image/png' or artifact['name'] == 'quality_report.json':
            result = client.post(review_url, json={'artifact_id': artifact['artifact_id'],
                'sha256': artifact['sha256'], 'verdict': 'pass', 'note': 'Synthetic test action only'})
            assert result.status_code == 200
    published = service.store.get_run(rid)
    assert published['status'] == 'COMPLETED_WITH_WARNINGS'
    assert all(a['status'] == 'superseded' for a in published['artifacts'] if a['artifact_id'] in {v['artifact_id'] for v in old})
    receipt = next(a for a in published['artifacts'] if a['name'] == 'human_review_receipt.json')
    receipt_data = client.get('/api/artifacts/' + receipt['artifact_id']).json()
    assert {r['artifact_id'] for r in receipt_data['reviews']} == {
        a['artifact_id'] for a in fresh if a['media_type'] == 'image/png' or a['name'] == 'quality_report.json'}
    assert len(published['reviews']) == 3  # Historical issue is retained, not used as a current blocker.
