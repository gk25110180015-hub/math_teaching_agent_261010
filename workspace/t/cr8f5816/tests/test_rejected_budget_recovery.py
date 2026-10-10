"""Offline recovery regression: real SQLite/state, synthetic proposals, no API/TeX."""
import copy
import json

import pytest

from math_agent.budget import BudgetIncrease
from math_agent.local_patch import LocalPatchError, apply_local_patch
from math_agent.local_recovery import LocalRecovery
from math_agent.pipeline import Pipeline
from math_agent.util import AgentError, digest, write_json
from test_draft_recovery import setup_pipeline
from test_local_recovery import Provider


pytestmark = pytest.mark.unit
UNIT = 'S01.U1'
KEY = 'unit:' + UNIT
CONTEXT = {'synthetic': 'rejected-proposal recovery, no remote model'}


def fixture(tmp_path, request_limit=60):
    provider = Provider()
    service, pipeline, plan = setup_pipeline(
        tmp_path, provider, max_requests_per_run=request_limit)
    base = provider.generate('writer_lecture_section', {}, None)
    draft = pipeline.build_root / 'rejected-budget-fixture'
    draft.mkdir()
    recovery = LocalRecovery(pipeline, plan['sections'][0], CONTEXT, base, plan, draft)
    recovery.state['pending_issues'] = [
        {'unit_id': UNIT, 'severity': 'review', 'message': 'Retained synthetic doubt'}]
    recovery.save()
    return service, pipeline, plan, recovery, base


def count_synthetic_request(pipeline):
    # Uses the production pre-send ledger; no actual HTTP request is made.
    pipeline.store.count_request(pipeline.job, pipeline.settings.max_requests_per_run,
                                {'fixture': 'OFFLINE_NO_MODEL_REQUEST', 'role': 'repair_local_patch'})


def reject_foreign_patch(pipeline, recovery):
    number = recovery.begin_proposal('strict_local_patch', [KEY], [UNIT])
    count_synthetic_request(pipeline)
    bad = {'section_id': 'S01', 'replacements': [
        {'unit_id': UNIT, 'tex': 'REJECTED TARGET BODY'},
        {'unit_id': 'S01.U2', 'tex': 'UNAUTHORIZED FOREIGN BODY'}]}
    evidence = recovery.folder / f'offline-rejected-proposal-{number}.json'
    write_json(evidence, bad)
    with pytest.raises(LocalPatchError) as rejected:
        apply_local_patch(recovery.candidate(), [UNIT], bad)
    recovery.reject(rejected.value)
    return evidence, digest(evidence.read_bytes())


def exhaust_two_rejections(pipeline, recovery):
    original_key = recovery.state['candidate_key']
    original_hash = recovery.state['candidate_hash']
    pending = copy.deepcopy(recovery.state['pending_issues'])
    evidence = [reject_foreign_patch(pipeline, recovery) for _ in range(2)]
    with pytest.raises(AgentError) as exhausted:
        recovery.begin_proposal('strict_local_patch', [KEY], [UNIT])
    assert exhausted.value.code == 'BUDGET_EXHAUSTED'
    assert recovery.state['candidate_key'] == original_key
    assert recovery.state['candidate_hash'] == original_hash
    assert recovery.state['pending_issues'] == pending
    assert recovery.state['proposal_counts_by_key'] == {KEY: 2}
    assert recovery.state['rejected_counts_by_key'] == {KEY: 2}
    assert recovery.state['unit_applied_counts'] == {}
    assert pipeline.store.get_run(pipeline.run['id'])['request_count'] == 2
    return evidence


def increase_and_resume(service, pipeline, plan, base, **changes):
    pipeline.store.finish(pipeline.job, 'BLOCKED', 'repair.section.S01',
                          {'code': 'BUDGET_EXHAUSTED', 'message': 'Offline rejected-proposal cap'})
    before = service.store.get_run(pipeline.run['id'])
    service.increase_budget(pipeline.run['id'], BudgetIncrease(
        expected_version=service.get_budget(pipeline.run['id'])['version'],
        expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'],
        action_id='offline-explicit-user-rejection-budget',
        note='Offline fixture representing explicit user approval; no live task is changed',
        **changes))
    assert service.store.get_run(pipeline.run['id']) == before
    service.retry(pipeline.run['id'])
    resumed = Pipeline(pipeline.settings, pipeline.store,
                       pipeline.store.claim('offline-rejected-budget-resume'))
    draft = resumed.build_root / 'resumed-rejected-budget-fixture'
    draft.mkdir()
    recovery = LocalRecovery(resumed, plan['sections'][0], CONTEXT, base, plan, draft)
    after = service.store.get_run(pipeline.run['id'])
    assert after['approval'] == before['approval']
    assert after['request_count'] == before['request_count'] == 2
    assert after['reviews'] == []
    assert recovery.state['proposal_calls'] == recovery.state['rejected_proposals'] == 2
    assert recovery.state['rejected_counts_by_key'] == {KEY: 2}
    assert recovery.state['unit_applied_counts'] == {}
    with service.store.connect() as connection:
        kinds = [row[0] for row in connection.execute(
            'SELECT type FROM events WHERE run_id=? ORDER BY sequence', (pipeline.run['id'],))]
    assert kinds.count('budget.increased_by_user') == kinds.count('job.retry') == 1
    return resumed, recovery


def test_default_two_rejections_stop_and_preserve_original_candidate(tmp_path):
    _, pipeline, _, recovery, base = fixture(tmp_path)
    evidence = exhaust_two_rejections(pipeline, recovery)
    assert recovery.candidate() == base
    for path, sha in evidence:
        assert digest(path.read_bytes()) == sha
    assert len(list((recovery.folder / 'history').glob('state-*.json'))) >= 4


def test_explicit_increase_resumes_rejected_key_without_erasing_counts_or_doubts(tmp_path):
    service, pipeline, plan, recovery, base = fixture(tmp_path)
    evidence = exhaust_two_rejections(pipeline, recovery)
    pending = copy.deepcopy(recovery.state['pending_issues'])
    resumed, recovery = increase_and_resume(
        service, pipeline, plan, base, local_repairs_per_unit=6)
    assert recovery.begin_proposal('strict_local_patch', [KEY], [UNIT]) == 3
    count_synthetic_request(resumed)
    patch = {'section_id': 'S01', 'replacements': [
        {'unit_id': UNIT, 'tex': base['units'][0]['tex'] + ' Clarified legal premise.'}]}
    fixed, _ = apply_local_patch(recovery.candidate(), [UNIT], patch)
    recovery.accept(fixed)
    assert recovery.candidate()['units'][1] == base['units'][1]
    assert 'REJECTED TARGET BODY' not in json.dumps(recovery.candidate())
    assert recovery.state['unit_applied_counts'] == {UNIT: 1}
    assert recovery.state['rejected_counts_by_key'] == {KEY: 2}
    assert recovery.state['proposal_counts_by_key'] == {KEY: 3}
    assert recovery.state['pending_issues'] == pending
    assert recovery.state['phase'] == 'UNCHECKED_REPAIRED'
    assert service.get_budget(pipeline.run['id'])['local_repairs_per_unit'] == 6
    assert service.store.get_run(pipeline.run['id'])['request_count'] == 3
    for path, sha in evidence:
        assert digest(path.read_bytes()) == sha


def test_increased_rejection_budget_is_still_finite_and_explains_its_limit(tmp_path):
    service, pipeline, plan, recovery, base = fixture(tmp_path)
    evidence = exhaust_two_rejections(pipeline, recovery)
    resumed, recovery = increase_and_resume(
        service, pipeline, plan, base, local_repairs_per_unit=6)
    evidence.extend(reject_foreign_patch(resumed, recovery) for _ in range(4))
    with pytest.raises(AgentError) as exhausted:
        recovery.begin_proposal('strict_local_patch', [KEY], [UNIT])
    assert exhausted.value.code == 'BUDGET_EXHAUSTED'
    assert 'rejection_limit=6' in exhausted.value.message
    assert recovery.state['proposal_calls'] == recovery.state['rejected_proposals'] == 6
    assert recovery.state['rejected_counts_by_key'] == {KEY: 6}
    assert recovery.candidate() == base
    assert service.store.get_run(pipeline.run['id'])['request_count'] == 6
    assert recovery.state['pending_issues']
    for path, sha in evidence:
        assert digest(path.read_bytes()) == sha


def test_request_only_increase_does_not_reset_local_rejection_budget(tmp_path):
    service, pipeline, plan, recovery, base = fixture(tmp_path)
    exhaust_two_rejections(pipeline, recovery)
    resumed, recovery = increase_and_resume(service, pipeline, plan, base, requests=240)
    with pytest.raises(AgentError) as exhausted:
        recovery.begin_proposal('strict_local_patch', [KEY], [UNIT])
    assert exhausted.value.code == 'BUDGET_EXHAUSTED'
    assert resumed.effective_budget()['local_repairs_per_unit'] == 2
    assert service.store.get_run(pipeline.run['id'])['request_count'] == 2


def test_local_increase_cannot_bypass_independent_request_ceiling(tmp_path):
    service, pipeline, plan, recovery, base = fixture(tmp_path, request_limit=2)
    exhaust_two_rejections(pipeline, recovery)
    resumed, recovery = increase_and_resume(
        service, pipeline, plan, base, local_repairs_per_unit=6)
    assert recovery.begin_proposal('strict_local_patch', [KEY], [UNIT]) == 3
    with pytest.raises(AgentError) as exhausted:
        count_synthetic_request(resumed)
    assert exhausted.value.code == 'BUDGET_EXHAUSTED'
    assert resumed.effective_budget()['requests'] == 2
    assert service.store.get_run(pipeline.run['id'])['request_count'] == 2
    assert recovery.candidate() == base
    assert recovery.state['unit_applied_counts'] == {}
