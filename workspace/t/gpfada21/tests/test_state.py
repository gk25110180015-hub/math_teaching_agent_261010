import json
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from math_agent.settings import Settings
from math_agent.store import Store
from math_agent.service import Service
from math_agent.domain import NewRun, ConfirmRequest, ExecuteRequest, DecisionsRequest, ReviewRequest
from math_agent.util import AgentError


@pytest.fixture
def service(tmp_path):
    return Service(Settings(workspace=tmp_path))


def ready(service):
    run = service.create(NewRun(workflow_id='lecture.generate', topic='数列极限', trusted_input=True))
    with service.store.transaction() as c:
        service.store.save_plan(c, run['id'], {
            'schema_version': 1, 'workflow_id': 'lecture.generate', 'input_snapshot_hash': run['input_hash'],
            'title': '数列极限', 'theme': 'default', 'sections': [{'id':'S01','title':'定义'}, {'id':'S02','title':'计算'}],
            'lecture': {'proof_policy':'key'}, 'questions': [], 'decisions': [], 'decision_ids':[],
            'unresolved_blocking_questions': [], 'omissions': [], 'additions': []})
    plan = service.store.get_run(run['id'])['plan']
    service.confirm(run['id'], ConfirmRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], action_id='click-confirm'))
    return run['id'], plan


def test_T11_double_execute_single_job(service):
    rid, p = ready(service)
    req = ExecuteRequest(expected_plan_revision=p['revision'], expected_plan_hash=p['hash'], idempotency_key='execute')
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: service.execute(rid, req), range(2)))
    assert results[0]['id'] == results[1]['id']
    assert len(service.store.get_run(rid)['jobs']) == 1


def test_T12_T13_failure_preserves_approval_retry(service):
    rid, p = ready(service)
    service.execute(rid, ExecuteRequest(expected_plan_revision=p['revision'], expected_plan_hash=p['hash'], idempotency_key='execute'))
    job = service.store.claim('one')
    service.store.checkpoint(job, 'S01', 'input', {'tex': 'passed section'})
    service.store.finish(job, 'FAILED', 'compile.section.S02', {'code': 'COMPILE_FAILED'})
    service.retry(rid)
    run = service.store.get_run(rid)
    assert run['status'] == 'QUEUED'
    assert run['approval']['hash'] == p['hash']
    assert service.store.cached_step(rid, 'S01', 'input')['tex'] == 'passed section'


def test_T14_stale_revision_conflict(service):
    rid, p = ready(service)
    with pytest.raises(AgentError) as exc:
        service.confirm(rid, ConfirmRequest(expected_plan_revision=0, expected_plan_hash=p['hash'], action_id='old'))
    assert exc.value.status == 409


def test_T15_restart_persists(service):
    rid, p = ready(service)
    other = Store(service.settings.db_path)
    assert other.get_run(rid)['approval']['hash'] == p['hash']


def test_T16_expired_worker_cannot_commit(service):
    rid, p = ready(service)
    service.execute(rid, ExecuteRequest(expected_plan_revision=p['revision'], expected_plan_hash=p['hash'], idempotency_key='execute'))
    old = service.store.claim('old')
    with service.store.transaction() as c:
        c.execute('UPDATE jobs SET lease_deadline=0 WHERE id=?', (old['id'],))
    new = service.store.claim('new')
    assert new['fencing_token'] > old['fencing_token']
    with pytest.raises(AgentError):
        service.store.checkpoint(old, 'S01', 'i', {'bad': True})


def test_T58_cancel_blocks_late_commit(service):
    rid, p = ready(service)
    service.execute(rid, ExecuteRequest(expected_plan_revision=p['revision'], expected_plan_hash=p['hash'], idempotency_key='execute'))
    job = service.store.claim('worker')
    service.cancel(rid)
    with pytest.raises(AgentError):
        service.store.checkpoint(job, 'late', 'i', {'late': True})
    assert service.store.get_run(rid)['status'] == 'CANCELLED'


def test_concurrent_database_migration(tmp_path):
    path=tmp_path/'concurrent.db'
    with ThreadPoolExecutor(2) as pool:
        stores=list(pool.map(lambda _:Store(path),range(2)))
    with stores[0].connect() as c:
        assert [row[0] for row in c.execute('SELECT version FROM schema_migrations ORDER BY version')]==[1,2]


def test_all_pages_and_quality_required_before_test_publication(service):
    """Simulated review actions test the gate; this is NOT human visual acceptance."""
    rid,p=ready(service)
    service.execute(rid,ExecuteRequest(expected_plan_revision=p['revision'],expected_plan_hash=p['hash'],idempotency_key='build'))
    job=service.store.claim('test-worker')
    service.store.publish_artifacts(job,[
        {'storage_key':'fixture-page-1','name':'page-1.png','sha256':'pagehash1','media_type':'image/png'},
        {'storage_key':'fixture-page-2','name':'page-2.png','sha256':'pagehash2','media_type':'image/png'},
        {'storage_key':'fixture-quality','name':'quality_report.json','sha256':'qualityhash','media_type':'application/json'}])
    service.store.finish(job,'AWAITING_USER_REVIEW','review.pages_and_quality')
    artifacts=service.store.get_run(rid)['artifacts']
    for a in artifacts[:-1]:
        service.review(rid,ReviewRequest(artifact_id=a['artifact_id'],sha256=a['sha256'],verdict='pass',note='AUTOMATED TEST ACTION, not human acceptance'))
        assert service.store.get_run(rid)['status']=='AWAITING_USER_REVIEW'
    a=artifacts[-1]
    service.review(rid,ReviewRequest(artifact_id=a['artifact_id'],sha256=a['sha256'],verdict='issue',note='Synthetic issue'))
    assert service.store.get_run(rid)['status']=='AWAITING_USER_REVIEW'
    service.review(rid,ReviewRequest(artifact_id=a['artifact_id'],sha256=a['sha256'],verdict='pass',note='AUTOMATED TEST ACTION, not human acceptance'))
    result=service.store.get_run(rid)
    assert result['status']=='COMPLETED_WITH_WARNINGS'
    assert any(a['name']=='human_review_receipt.json' for a in result['artifacts'])
