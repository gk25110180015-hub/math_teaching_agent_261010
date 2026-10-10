"""Formal local feedback API -> queued Pipeline -> whole chapter scoped repair.

Actual SQLite, approvals and TestClient; synthetic provider/compiler only.
"""
import json

import pytest
from fastapi.testclient import TestClient

from math_agent.pipeline import Pipeline
from math_agent.util import digest
from math_agent.web.app import create_app
from test_automatic_recheck_api import payload, publish_synthetic
from test_recheck_feedback_pipeline import FeedbackProvider
from test_teaching_quality_gate import teaching_setup


pytestmark = pytest.mark.unit


@pytest.mark.parametrize('source', ['user', 'agent_audit'])
def test_actual_api_event_reaches_current_build_review_then_approved_scoped_repair(tmp_path, monkeypatch, source):
    provider = FeedbackProvider()
    service, pipeline, plan, compiles = teaching_setup(tmp_path, monkeypatch, provider)
    rid = pipeline.run['id']
    initial, _ = pipeline.lecture(plan)
    service.store.count_request(pipeline.job, 60, {'fixture': 'SYNTHETIC_EXISTING_REQUEST_COUNT_NO_REMOTE_CALL'})
    publish_synthetic(service.store, pipeline.settings, pipeline.job, 'initial-offline-feedback-delivery')
    service.store.finish(pipeline.job, 'AWAITING_USER_REVIEW', 'review.pages_and_quality')
    before = service.get(rid)
    feedback = '请核对已批准的一般参数域和边界；目前的固定参数例子可能不足。'
    with TestClient(create_app(pipeline.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['X-CSRF-Token'] = client.get('/api/session').json()['csrf_token']
        result = client.post(f'/api/runs/{rid}/recheck',
                             json={**payload(plan), 'feedback': feedback, 'feedback_source': source})
        assert result.status_code == 202, result.text
        new_job = result.json()
        claimed = service.store.claim('offline-feedback-integration-worker')
        assert claimed['id'] == new_job['id'] and claimed['id'] != pipeline.job['id']
        resumed = Pipeline(pipeline.settings, service.store, claimed)
        resumed.provider = provider
        generated, reports = resumed.lecture(plan)
        service.store.finish(claimed, 'AWAITING_USER_REVIEW', 'offline.review_complete_no_teacher_action')
        history = client.get(f'/api/runs/{rid}/events').json()
        actions = [value for value in history if value['type'] == 'checks.rerun_requested']
        assert len(actions) == 1
        event = actions[0]
        contexts = [context for context in provider.reviews
                    if context['scope']['kind'] == 'chapter_coverage' and context.get('recheck_feedback')]
        assert len(contexts) == 2  # Failing body and repaired body both reviewed.
        for context in contexts:
            actual = context['recheck_feedback']
            assert actual['feedback'] == feedback and actual['feedback_source'] == source
            assert actual['source_event']['sequence'] == event['sequence']
            assert actual['source_event']['payload_sha256'] == digest(event['payload_json'])
            assert actual['source_event']['job_id'] == new_job['id']
            assert actual['source_event']['plan_hash'] == before['approval']['hash']
            assert 'not proof' in actual['instruction']
        assert contexts[0]['units'] == [unit for _, section in initial for unit in section['units']]
        assert len(provider.repairs) == 1 and provider.repairs[0]['allowed_unit_ids'] == ['S02.U01']
        assert provider.writes == ['S01', 'S02'] and len(compiles) == 3
        assert generated[0] == initial[0] and '模拟补全' in generated[1][1]['units'][0]['tex']
        coverage = next(item['chapter_coverage'] for item in reports if 'chapter_coverage' in item)
        evidence = coverage['recheck_feedback_evidence']
        evidence_path = pipeline.settings.workspace / evidence['storage_key']
        saved = json.loads(evidence_path.read_bytes())
        assert digest(evidence_path.read_bytes()) == evidence['sha256']
        assert saved['source_action'] == event['payload']
        assert saved['unit_hashes'] == {unit['id']: digest(unit) for _, section in generated for unit in section['units']}
        current = service.get(rid)
        for key in ('approval', 'plan', 'input_hash', 'request_count', 'reviews', 'budget'):
            assert current[key] == before[key], key
        assert current['reviews'] == [] and current['request_count'] == 1
        assert not any(value['type'] == 'human.review' for value in history)
        assert all(value['status'] == 'superseded' for value in current['artifacts'])
        for artifact in before['artifacts']:
            old = client.get('/api/artifacts/' + artifact['artifact_id'])
            assert old.status_code == 200 and digest(old.content) == artifact['sha256']
