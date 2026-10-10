"""Offline explicit-user budgets and immutable partial checkpoint delivery."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from math_agent.budget import BudgetIncrease
from math_agent.domain import ConfirmRequest, ExecuteRequest, NewRun
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import AgentError, canonical, digest, write_json
from math_agent.web.app import create_app

pytestmark = pytest.mark.unit


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('MATH_AGENT_API_KEY', '')
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')
    settings = Settings(workspace=tmp_path / 'w', reference_root=tmp_path / 'refs', max_requests_per_run=2)
    app = create_app(settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.headers['X-CSRF-Token'] = client.get('/api/session').json()['csrf_token']
        service = app.state.service
        run = service.create(NewRun(workflow_id='lecture.generate', topic='Offline budget fixture', trusted_input=True))
        rid = run['id']
        with service.store.transaction() as connection:
            service.store.save_plan(connection, rid, {'title': 'Budget fixture', 'provider': 'mock',
                'sections': [{'id': 'S01', 'title': 'One'}], 'questions': [], 'unresolved_blocking_questions': []})
        plan = service.store.get_run(rid)['plan']
        service.confirm(rid, ConfirmRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], action_id='fixture'))
        service.execute(rid, ExecuteRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], idempotency_key='fixture'))
        job = service.store.claim('offline-budget-test')
        service.store.initialize_budget(job, {'requests': 2, 'local_repairs_per_unit': 2, 'global_repair_rounds': 2})
        for _ in range(2): service.store.count_request(job, 2, {'fixture': 'OFFLINE_NO_MODEL_REQUEST'})
        with pytest.raises(AgentError) as exhausted:
            service.store.count_request(job, 2, {'fixture': 'OFFLINE_NO_MODEL_REQUEST'})
        assert exhausted.value.code == 'BUDGET_EXHAUSTED'
        draft = settings.workspace / 'b' / rid[:16] / 'sS01_fixture'
        source = draft / 'source' / 'lecture.tex'; source.parent.mkdir(parents=True)
        source.write_bytes(b'Partial source: offline fixture, not compiled')
        pdf = draft / 'build' / 'lecture.pdf'; pdf.parent.mkdir()
        pdf.write_bytes(b'%PDF-1.4\nSynthetic API hash fixture; not a compiled document.\n')
        checkpoint = {'generated': {'section_id': 'S01', 'units': [{'id': 'U1', 'kind': 'definition', 'tex': 'Fixture'}]},
            'source_key': source.relative_to(settings.workspace).as_posix(), 'source_hash': digest(source.read_bytes()),
            'report': {'compile': {'status': 'PASS', 'fixture': 'MOCK_COMPILER', 'pdf_path': str(pdf), 'pdf_sha256': digest(pdf.read_bytes())}}}
        service.store.checkpoint(job, 'section.S01', 'fixture-input', checkpoint)
        diagnostic = settings.workspace / 'runs' / rid / 'fixture-diagnostic.json'
        write_json(diagnostic, {'code': 'BUDGET_EXHAUSTED', 'fixture': True})
        service.store.publish_artifacts(job, [{'storage_key': diagnostic.relative_to(settings.workspace).as_posix(),
            'name': 'failure_diagnostic.json', 'sha256': digest(diagnostic.read_bytes()), 'media_type': 'application/json', 'metadata': {'fixture': True}}])
        service.store.finish(job, 'BLOCKED', 'review.section.S02', {'code': 'BUDGET_EXHAUSTED', 'message': 'Offline request counter fixture'})
        yield client, service, rid, job, checkpoint, source, pdf


def payload(service, rid, **changes):
    run = service.store.get_run(rid)
    return {'expected_version': service.get_budget(rid)['version'], 'expected_plan_revision': run['active_plan_revision'],
        'expected_plan_hash': run['plan']['hash'], 'requests': 3, 'action_id': 'explicit-user-1',
        'note': 'Offline explicit budget choice', **changes}


def test_explicit_increase_preserves_count_approval_error_artifacts_and_never_enqueues(setup):
    client, service, rid, *_ = setup
    before = service.store.get_run(rid)
    response = client.post(f'/api/runs/{rid}/budget', json=payload(service, rid))
    assert response.status_code == 200 and response.json()['requests'] == 3
    assert response.json()['request_count'] == 2 and response.json()['version'] == 1
    assert service.store.get_run(rid) == before
    with service.store.connect() as connection:
        audit = dict(connection.execute('SELECT * FROM budget_actions WHERE run_id=?', (rid,)).fetchone())
        assert audit['actor'] == 'local_user' and audit['note'] == 'Offline explicit budget choice'
        assert connection.execute("SELECT count(*) FROM events WHERE run_id=? AND type='budget.increased_by_user'", (rid,)).fetchone()[0] == 1
    assert client.post(f'/api/runs/{rid}/retry', json={}).status_code == 202
    resumed = service.store.get_run(rid)
    assert resumed['approval'] == before['approval'] and resumed['request_count'] == 2 and resumed['reviews'] == []


def test_retry_cannot_reset_exhausted_budget_without_explicit_user_action(setup):
    client, service, rid, *_ = setup
    before = service.store.get_run(rid)
    response = client.post(f'/api/runs/{rid}/retry', json={})
    assert response.status_code == 409 and response.json()['error']['code'] == 'BUDGET_EXHAUSTED'
    assert service.store.get_run(rid) == before


def test_idempotent_replay_does_not_increase_again_or_erase_failed_records(setup):
    client, service, rid, *_ = setup
    request = payload(service, rid)
    one = client.post(f'/api/runs/{rid}/budget', json=request)
    two = client.post(f'/api/runs/{rid}/budget', json=request)
    assert one.json() == two.json()
    assert client.post(f'/api/runs/{rid}/budget', json={**request, 'requests': 4}).status_code == 409
    assert service.get_budget(rid)['version'] == 1


@pytest.mark.parametrize('field', ['requests', 'local_repairs_per_unit', 'global_repair_rounds'])
@pytest.mark.parametrize('value', [True, '3', 2.5, -1, 0, 1001])
def test_ambiguous_or_out_of_bounds_budget_values_rejected(setup, field, value):
    client, service, rid, *_ = setup
    request = payload(service, rid, **{field: value})
    assert client.post(f'/api/runs/{rid}/budget', json=request).status_code == 422
    assert service.get_budget(rid)['version'] == 0


@pytest.mark.parametrize('changes', [{'requests': 2}, {'requests': 1}, {'expected_version': 99},
                                     {'expected_plan_hash': 'stale'}, {'expected_plan_revision': 99}])
def test_decrease_unchanged_or_stale_preconditions_rejected(setup, changes):
    client, service, rid, *_ = setup
    assert client.post(f'/api/runs/{rid}/budget', json=payload(service, rid, **changes)).status_code in (400, 409)
    assert service.get_budget(rid)['version'] == 0


def test_only_blocked_and_no_active_job_and_local_user_may_increase(setup):
    client, service, rid, job, *_ = setup
    request = payload(service, rid)
    benchmark = Service(service.settings, actor='benchmark_driver')
    with pytest.raises(AgentError) as error: benchmark.increase_budget(rid, BudgetIncrease.model_validate(request))
    assert error.value.status == 403
    with service.store.transaction() as connection:
        connection.execute("UPDATE jobs SET status='queued' WHERE id=?", (job['id'],))
    assert client.post(f'/api/runs/{rid}/budget', json=request).status_code == 409
    with service.store.transaction() as connection:
        connection.execute("UPDATE jobs SET status='failed' WHERE id=?", (job['id'],))
        connection.execute("UPDATE runs SET status='FAILED' WHERE id=?", (rid,))
    assert client.post(f'/api/runs/{rid}/budget', json=request).status_code == 409


def test_budget_endpoint_requires_session_csrf_and_same_origin(setup):
    client, service, rid, *_ = setup
    request = payload(service, rid)
    assert client.post(f'/api/runs/{rid}/budget', json=request, headers={'X-CSRF-Token': ''}).status_code == 403
    assert client.post(f'/api/runs/{rid}/budget', json=request, headers={'Origin': 'https://foreign.example'}).status_code == 403
    client.cookies.clear()
    assert client.get(f'/api/runs/{rid}/budget').status_code == 403


def test_persisted_initial_budget_is_not_raised_by_different_service_defaults(setup):
    _, service, rid, *_ = setup
    other = Service(service.settings.model_copy(update={'max_requests_per_run': 120}))
    assert other.get_budget(rid)['requests'] == 2
    assert other.get_budget(rid)['defaults']['requests'] == 2
    other.increase_budget(rid, BudgetIncrease.model_validate(payload(other, rid, requests=3)))
    assert service.get_budget(rid)['requests'] == 3


def test_override_can_resume_requests_but_caller_hard_cap_remains_independent(setup):
    _, service, rid, _, *_ = setup
    service.increase_budget(rid, BudgetIncrease.model_validate(payload(service, rid, requests=8)))
    service.retry(rid); job = service.store.claim('resumed-budget-fixture')
    service.store.initialize_budget(job, {'requests': 60, 'local_repairs_per_unit': 2, 'global_repair_rounds': 2})
    assert service.get_budget(rid)['defaults']['requests'] == 2
    with pytest.raises(AgentError) as error:
        service.store.count_request(job, 60, {'fixture': True}, hard_limit=2)
    assert error.value.code == 'BUDGET_EXHAUSTED' and service.store.get_run(rid)['request_count'] == 2
    service.store.count_request(job, 60, {'fixture': True}, hard_limit=3)
    with pytest.raises(AgentError): service.store.count_request(job, 60, {'fixture': True}, hard_limit=3)
    assert service.store.get_run(rid)['request_count'] == 3


def test_partial_source_pdf_json_are_hash_checked_and_not_teacher_artifacts(setup):
    client, service, rid, _, _, source, pdf = setup
    before = service.store.get_run(rid)
    run = client.get(f'/api/runs/{rid}').json()
    assert run['budget']['request_count'] == 2 and run['budget']['can_increase']
    item = run['partial_checkpoints'][0]
    assert item['status'] == 'PARTIAL' and item['teacher_review'] == 'NOT_RUN'
    assert item['plan_binding'] == 'UNKNOWN' and item['created_at'] and item['checkpoint_hash']
    assert {file['kind'] for file in item['downloads']} == {'source', 'pdf', 'checkpoint'}
    for artifact in item['downloads']:
        response = client.get(artifact['url'])
        assert response.status_code == 200
        assert digest(response.content) == artifact['sha256'] == response.headers['X-Content-SHA256']
        assert response.headers['X-Math-Agent-Status'] == 'PARTIAL'
    assert service.store.get_run(rid) == before


@pytest.mark.parametrize('fault', ['source_changed', 'pdf_changed', 'checkpoint_hash', 'foreign_source', 'foreign_pdf'])
def test_partial_download_blocks_tamper_and_foreign_run_paths(setup, fault):
    client, service, rid, _, checkpoint, source, pdf = setup
    original_link = client.get(f'/api/runs/{rid}/partials').json()[0]['downloads'][0]['url']
    altered = copy.deepcopy(checkpoint)
    if fault == 'source_changed': source.write_bytes(b'changed')
    elif fault == 'pdf_changed': pdf.write_bytes(b'%PDF-modified')
    elif fault == 'foreign_source':
        foreign = service.settings.workspace / 'b' / ('f' * 16) / 'sS01_other' / 'source' / 'lecture.tex'
        foreign.parent.mkdir(parents=True); foreign.write_bytes(source.read_bytes())
        altered['source_key'] = foreign.relative_to(service.settings.workspace).as_posix()
    elif fault == 'foreign_pdf':
        foreign = service.settings.workspace / 'b' / ('f' * 16) / 'lecture.pdf'
        foreign.parent.mkdir(parents=True); foreign.write_bytes(pdf.read_bytes())
        altered['report']['compile']['pdf_path'] = str(foreign)
    with service.store.transaction() as connection:
        connection.execute('UPDATE steps SET output_json=?,output_hash=? WHERE run_id=?',
            (canonical(altered), 'bad-hash' if fault == 'checkpoint_hash' else digest(altered), rid))
    item = client.get(f'/api/runs/{rid}/partials').json()[0]
    assert item['status'] == 'PARTIAL_UNAVAILABLE' and item['downloads'] == []
    assert client.get(original_link).status_code == 404
    assert client.get(f'/api/runs/{rid}/partials/../../agent.db').status_code == 404


def make_legacy(service, rid):
    with service.store.transaction() as connection:
        connection.execute('DELETE FROM run_budgets WHERE run_id=?', (rid,))
    return Service(service.settings.model_copy(update={'max_requests_per_run': 120}))


def legacy_evidence(service, rid, **changes):
    state = {'workspace': str(service.settings.workspace), 'cases': {'fixture': {
        'run_id': rid, 'request_count': 2, 'effective_request_limit': 2,
        'request_metrics': {'request_count': 2, 'request_limit': 2}}}, **changes}
    path = service.settings.workspace / 'legacy-fixture-state.json'
    write_json(path, state)
    return path, digest(path.read_bytes())


def test_true_legacy_requests_never_silently_inherit_new_service_default(setup):
    client, service, rid, job, *_ = setup
    other = make_legacy(service, rid)
    before = service.store.get_run(rid)
    assert other.get_budget(rid)['requests'] is None
    assert other.get_budget(rid)['baseline_unknown']
    for request in [payload(other, rid, requests=None, local_repairs_per_unit=3), payload(other, rid, requests=3)]:
        with pytest.raises(AgentError) as error:
            other.increase_budget(rid, BudgetIncrease.model_validate(request))
        assert error.value.code == 'BUDGET_BASELINE_UNKNOWN'
    with pytest.raises(AgentError) as error: other.retry(rid)
    assert error.value.code == 'BUDGET_BASELINE_UNKNOWN'
    assert service.store.get_run(rid) == before
    # Simulate a legacy job already queued when upgraded. Worker must block before
    # counting/calling any provider; this does not run a model.
    with service.store.transaction() as connection:
        connection.execute("UPDATE jobs SET status='queued' WHERE id=?", (job['id'],))
    claimed = service.store.claim('legacy-fixture')
    with pytest.raises(AgentError) as error:
        other.store.initialize_budget(claimed, {'requests': 120, 'local_repairs_per_unit': 2, 'global_repair_rounds': 2})
    assert error.value.code == 'BUDGET_BASELINE_UNKNOWN'
    assert other.get_budget(rid)['requests'] is None and other.get_budget(rid)['request_count'] == 2


def test_unknown_history_user_must_explicitly_confirm_new_request_limit(setup):
    client, service, rid, *_ = setup
    other = make_legacy(service, rid)
    before = service.store.get_run(rid)
    request = payload(other, rid, requests=3, confirm_unknown_request_limit=True)
    response = client.post(f'/api/runs/{rid}/budget', json=request)
    assert response.status_code == 200
    assert response.json()['requests'] == 3 and not response.json()['baseline_unknown']
    assert response.json()['defaults']['requests'] == 3
    assert response.json()['source'] == 'EXPLICIT_USER_NEW_LIMIT_HISTORY_UNKNOWN'
    assert service.store.get_run(rid) == before
    with service.store.connect() as connection:
        audit = json.loads(connection.execute("SELECT payload_json FROM events WHERE run_id=? AND type='budget.increased_by_user'", (rid,)).fetchone()[0])
    assert audit['request_limit_action'] == 'NEW_CONFIRMED_LIMIT_HISTORY_UNKNOWN'


def test_verified_legacy_import_restores_only_known_limit_without_expansion_or_execution(setup):
    _, service, rid, *_ = setup
    other = make_legacy(service, rid)
    path, sha = legacy_evidence(service, rid)
    before = service.store.get_run(rid)
    result = other.import_legacy_request_budget(rid, path, sha)
    assert result['requests'] == 2 and result['version'] == 0 and result['request_count'] == 2
    assert result['initialized_fields'] == ['requests']
    assert result['source'] == 'VERIFIED_BENCHMARK_STATE'
    assert service.store.get_run(rid) == before
    assert other.get_budget(rid)['requests'] == 2
    with service.store.connect() as connection:
        audit = json.loads(connection.execute("SELECT payload_json FROM events WHERE run_id=? AND type='budget.legacy_requests_imported'", (rid,)).fetchone()[0])
    assert audit['evidence_sha256'] == sha and audit['actor'] == 'local_user'
    assert audit['local_global_historical_limits'] == 'UNKNOWN'
    with pytest.raises(AgentError) as error: other.import_legacy_request_budget(rid, path, sha)
    assert error.value.code == 'BUDGET_ALREADY_INITIALIZED'


@pytest.mark.parametrize('fault', ['sha', 'workspace', 'count', 'metric_count', 'limit', 'duplicate', 'actor', 'active'])
def test_legacy_evidence_must_match_hash_workspace_run_counts_and_both_limits(setup, fault):
    _, service, rid, job, *_ = setup
    other = make_legacy(service, rid)
    path, sha = legacy_evidence(service, rid)
    state = json.loads(path.read_text(encoding='utf-8'))
    if fault == 'workspace': state['workspace'] = str(service.settings.workspace / 'other')
    if fault == 'count': state['cases']['fixture']['request_count'] = state['cases']['fixture']['request_metrics']['request_count'] = 1
    if fault == 'metric_count': state['cases']['fixture']['request_metrics']['request_count'] = 1
    if fault == 'limit': state['cases']['fixture']['request_metrics']['request_limit'] = 120
    if fault == 'duplicate': state['cases']['other'] = copy.deepcopy(state['cases']['fixture'])
    if fault == 'actor': other = Service(other.settings, actor='benchmark_driver')
    if fault == 'active':
        with service.store.transaction() as connection:
            connection.execute("UPDATE jobs SET status='queued' WHERE id=?", (job['id'],))
    write_json(path, state)
    sha = 'wrong' if fault == 'sha' else digest(path.read_bytes())
    with pytest.raises(AgentError): other.import_legacy_request_budget(rid, path, sha)
    assert other.get_budget(rid)['requests'] is None
    assert other.get_budget(rid)['request_count'] == 2


@pytest.mark.parametrize('binding', ['CURRENT', 'STALE'])
def test_partial_plan_binding_uses_only_recorded_checkpoint_identity(setup, binding):
    client, service, rid, _, checkpoint, *_ = setup
    plan = service.store.get_run(rid)['plan']
    checkpoint = {**checkpoint, 'plan_hash': plan['hash'] if binding == 'CURRENT' else 'different-plan',
                  'plan_revision': plan['revision']}
    with service.store.transaction() as connection:
        connection.execute('UPDATE steps SET output_json=?,output_hash=? WHERE run_id=?', (canonical(checkpoint), digest(checkpoint), rid))
    assert client.get(f'/api/runs/{rid}/partials').json()[0]['plan_binding'] == binding
