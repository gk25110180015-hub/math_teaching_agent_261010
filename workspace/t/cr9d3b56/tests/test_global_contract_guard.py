"""Offline guard against resetting same-plan repair counts on contract changes."""
import copy
import json

import pytest

from math_agent.domain import ConfirmRequest, ExecuteRequest
from math_agent.pipeline import Pipeline
from math_agent.util import AgentError
from test_global_budget_resume import exhausted_fixture


pytestmark = pytest.mark.unit


@pytest.mark.parametrize('changed_field', ['repair_prompt_hash', 'written_schema_hash', 'normalizer_hash'])
def test_changed_global_contract_blocks_without_resetting_same_approved_plan_state(tmp_path, monkeypatch, changed_field):
    service, pipeline, plan, _, _, _, calls = exhausted_fixture(tmp_path, monkeypatch)
    path = pipeline.root / 'global-repair-state.json'
    raw = path.read_bytes()
    stored = json.loads(raw)
    before = service.store.get_run(pipeline.run['id'])
    changed = {**pipeline._global_repair_identity(plan), changed_field: 'updated-contract-fixture'}
    monkeypatch.setattr(pipeline, '_global_repair_identity', lambda _: changed)
    calls_before = len(calls)
    with pytest.raises(AgentError) as error:
        pipeline._load_global_repair_state(plan)
    assert error.value.code == 'GLOBAL_REPAIR_CONTRACT_CHANGED'
    assert path.read_bytes() == raw
    assert stored['rounds_used'] == 2 and stored['issues']
    assert stored['phase'] == 'budget_exhausted'
    assert service.store.get_run(pipeline.run['id']) == before
    assert len(calls) == calls_before


def test_different_explicitly_approved_plan_gets_fresh_global_state_only(tmp_path, monkeypatch):
    service, pipeline, plan, _, _, _, calls = exhausted_fixture(tmp_path, monkeypatch)
    path = pipeline.root / 'global-repair-state.json'
    old_bytes = path.read_bytes()
    request_count = service.store.get_run(pipeline.run['id'])['request_count']
    service.store.finish(pipeline.job, 'BLOCKED', 'math.global_interfaces', {'code': 'BUDGET_EXHAUSTED'})
    # Fixture a different plan through the real versioned Store and explicit
    # Service confirmation. No old approval is inferred for the new plan.
    changed = copy.deepcopy(plan)
    changed['title'] = 'A newly approved plan fixture'
    with service.store.transaction() as connection:
        service.store.save_plan(connection, pipeline.run['id'], changed)
    new_plan = service.store.get_run(pipeline.run['id'])['plan']
    assert new_plan['hash'] != plan['hash']
    service.confirm(pipeline.run['id'], ConfirmRequest(
        expected_plan_revision=new_plan['revision'], expected_plan_hash=new_plan['hash'],
        action_id='offline-new-explicit-plan-confirmation'))
    service.execute(pipeline.run['id'], ExecuteRequest(
        expected_plan_revision=new_plan['revision'], expected_plan_hash=new_plan['hash'],
        idempotency_key='offline-new-approved-plan-build'))
    next_pipeline = Pipeline(pipeline.settings, pipeline.store, pipeline.store.claim('offline-new-plan-check'))
    count = len(calls)
    state = next_pipeline._load_global_repair_state(new_plan)
    assert state['identity']['plan_hash'] == new_plan['hash']
    assert state['rounds_used'] == 0 and state['phase'] == 'not_started'
    assert state['sections'] == {} and state['pending'] == [] and not state.get('issues')
    assert path.read_bytes() == old_bytes  # Historical failure is retained, not overwritten by loading.
    current = service.store.get_run(pipeline.run['id'])
    assert current['approval']['hash'] == new_plan['hash']
    assert current['request_count'] == request_count and current['reviews'] == []
    assert len(calls) == count
