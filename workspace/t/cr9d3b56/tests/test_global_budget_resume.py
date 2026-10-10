"""Offline global-budget resumption; actual Store/Service, fake model/compiler."""
import copy
import json

import pytest

from math_agent.budget import BudgetIncrease
from math_agent.pipeline import Pipeline
from math_agent.util import AgentError, digest, write_json
from test_global_repair import GlobalRepairProvider, setup


pytestmark = pytest.mark.unit


def exhausted_fixture(tmp_path, monkeypatch):
    provider = GlobalRepairProvider('no_progress')
    service, pipeline, plan, compiles = setup(tmp_path, provider, monkeypatch, limit=2)
    active = [pipeline]
    calls = []
    generate = provider.generate
    def counted(role, context, schema):
        current = active[0]
        current.store.count_request(current.job, current.settings.max_requests_per_run,
                                    {'role': role, 'fixture': 'OFFLINE_NO_MODEL_HTTP'})
        calls.append(role)
        return generate(role, context, schema)
    provider.generate = counted
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'BUDGET_EXHAUSTED'
    state = json.loads((pipeline.root / 'global-repair-state.json').read_bytes())
    assert state['phase'] == 'budget_exhausted' and state['rounds_used'] == 2
    assert len(provider.repairs) == 2
    return service, pipeline, plan, provider, compiles, active, calls


def increase_resume(service, pipeline, plan, provider, active, **updates):
    service.store.finish(pipeline.job, 'BLOCKED', 'math.global_interfaces',
                         {'code': 'BUDGET_EXHAUSTED', 'message': 'Offline global round cap'})
    before = service.store.get_run(pipeline.run['id'])
    service.increase_budget(pipeline.run['id'], BudgetIncrease(
        expected_version=service.get_budget(pipeline.run['id'])['version'],
        expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'],
        action_id='offline-approved-global-budget', note='Offline explicit user increase fixture', **updates))
    assert service.store.get_run(pipeline.run['id']) == before
    service.retry(pipeline.run['id'])
    resumed = Pipeline(pipeline.settings, pipeline.store, pipeline.store.claim('offline-global-budget-resume'))
    resumed.provider = provider
    active[0] = resumed
    assert service.store.get_run(pipeline.run['id'])['request_count'] == before['request_count']
    assert service.store.get_run(pipeline.run['id'])['approval'] == before['approval']
    return resumed, before


def test_unchanged_global_budget_still_blocks_without_model_calls_or_state_reset(tmp_path, monkeypatch):
    _, pipeline, plan, _, _, _, calls = exhausted_fixture(tmp_path, monkeypatch)
    state_path = pipeline.root / 'global-repair-state.json'
    before = state_path.read_bytes()
    requests = pipeline.store.get_run(pipeline.run['id'])['request_count']
    call_count = len(calls)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'BUDGET_EXHAUSTED'
    assert state_path.read_bytes() == before
    assert len(calls) == call_count
    assert pipeline.store.get_run(pipeline.run['id'])['request_count'] == requests


def test_explicit_global_increase_repairs_preserved_concern_before_fresh_checks(tmp_path, monkeypatch):
    service, pipeline, plan, provider, compiles, active, calls = exhausted_fixture(tmp_path, monkeypatch)
    state_before = json.loads((pipeline.root / 'global-repair-state.json').read_bytes())
    failure_path = pipeline.root / 'global_review_failure.json'
    failure_before = failure_path.read_bytes()
    old_candidates = {path: digest(path.read_bytes()) for path in (pipeline.root / 'global-repairs').rglob('*-candidate.json')}
    old_compiles = list(compiles)
    old_locals = list(provider.locals)
    provider.mode = 'fix'
    resumed, before = increase_resume(service, pipeline, plan, provider, active, global_repair_rounds=6)
    call_count = len(calls)
    completed, _ = resumed.lecture(plan)
    assert calls[call_count] == 'repair_local_patch'  # No fresh reviewer lottery on an unchanged failing body.
    assert len(provider.repairs) == 3
    assert provider.repairs[-1]['issues'] == json.loads(failure_before)['issues']
    assert provider.writes == ['S01', 'S02']
    assert provider.locals == old_locals + ['S01', 'S02']
    assert len(compiles) == len(old_compiles) + 2
    assert not set(compiles[-2:]).intersection(old_compiles)
    assert '阿基米德' in completed[0][1]['units'][0]['tex']
    after = service.store.get_run(pipeline.run['id'])
    state_after = json.loads((pipeline.root / 'global-repair-state.json').read_bytes())
    assert state_before['rounds_used'] == 2 and state_after['rounds_used'] == 3
    assert state_after['phase'] == 'validated'
    assert service.get_budget(pipeline.run['id'])['global_repair_rounds'] == 6
    assert after['approval'] == before['approval'] and after['reviews'] == []
    assert after['request_count'] == len(calls) > before['request_count']
    assert failure_path.read_bytes() == failure_before
    assert all(digest(path.read_bytes()) == value for path, value in old_candidates.items())
    with service.store.connect() as connection:
        event = connection.execute("SELECT payload_json FROM events WHERE run_id=? AND type='global.budget_resumed'",
                                   (pipeline.run['id'],)).fetchone()
    assert event is not None
    evidence = json.loads(event[0])
    assert evidence['rounds_used_before'] == 2 and evidence['rounds_used_after'] == 3
    assert evidence['request_count_preserved'] == before['request_count']


def test_request_only_increase_does_not_unlock_global_rounds(tmp_path, monkeypatch):
    service, pipeline, plan, provider, _, active, calls = exhausted_fixture(tmp_path, monkeypatch)
    resumed, before = increase_resume(service, pipeline, plan, provider, active, requests=240)
    raw = (pipeline.root / 'global-repair-state.json').read_bytes()
    count = len(calls)
    with pytest.raises(AgentError) as error:
        resumed.lecture(plan)
    assert error.value.code == 'BUDGET_EXHAUSTED'
    assert service.get_budget(pipeline.run['id'])['global_repair_rounds'] == 2
    assert (pipeline.root / 'global-repair-state.json').read_bytes() == raw
    assert len(calls) == count
    assert service.store.get_run(pipeline.run['id'])['request_count'] == before['request_count']


@pytest.mark.parametrize('corruption', ['missing_failure', 'round_mismatch', 'body_hash'])
def test_increased_global_budget_cannot_skip_unverified_failure_evidence(tmp_path, monkeypatch, corruption):
    service, pipeline, plan, provider, _, active, calls = exhausted_fixture(tmp_path, monkeypatch)
    resumed, before = increase_resume(service, pipeline, plan, provider, active, global_repair_rounds=6)
    path = pipeline.root / 'global_review_failure.json'
    if corruption == 'missing_failure':
        path.rename(path.with_name('preserved-but-missing-pointer.json'))
    else:
        data = json.loads(path.read_bytes())
        if corruption == 'round_mismatch': data['rounds_used'] = 1
        else: data['unit_hashes']['S01.U01'] = 'changed'
        write_json(path, data)
    raw = (pipeline.root / 'global-repair-state.json').read_bytes()
    count = len(calls)
    with pytest.raises(AgentError) as error:
        resumed.lecture(plan)
    assert error.value.code == 'GLOBAL_REPAIR_LEGACY_UNVERIFIED'
    assert (pipeline.root / 'global-repair-state.json').read_bytes() == raw
    assert len(calls) == count
    assert service.store.get_run(pipeline.run['id'])['request_count'] == before['request_count']
