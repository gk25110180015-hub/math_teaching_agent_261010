"""Formal guided resume after accepted repairs must preserve its bound state.

All model/compile calls are injected; HTTP uses the local TestClient and SQLite
uses pytest's isolated workspace. No live task or production database is touched.
"""
import copy
import json
import os

import pytest

from math_agent import repair_guidance as guidance
from math_agent.local_recovery import LocalRecovery
from math_agent.pipeline import Pipeline
from math_agent.util import AgentError, digest, within, write_json
from test_local_recovery import Provider, direct_recovery, state
from test_repair_guidance import events, request_and_resume
from test_repair_guidance_api import blocked, payload


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith(('MATH_AGENT_', 'OPENAI_', 'DEEPSEEK_')):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')


def accepted_recovery(tmp_path, rounds=1):
    pipeline, plan, recovery = direct_recovery(tmp_path)
    original = recovery.candidate()
    for number in range(1, rounds + 1):
        recovery.begin_proposal('strict_local_patch', ['unit:S01.U1'], ['S01.U1'])
        changed = recovery.candidate()
        changed['units'][0]['tex'] += f' 第{number}轮已接受正文补充。'
        proposal = recovery.draft / f'accepted-proposal-{number}.json'
        write_json(proposal, {'round': number, 'target': 'S01.U1', 'candidate_sha256': digest(changed)})
        recovery.accept(changed, patch_evidence={'proposal_key': proposal.relative_to(pipeline.settings.workspace).as_posix()})
    pending = [{'unit_id': 'S01.U1', 'severity': 'review', 'message': '已接受的修复仍有尚未解决的原数学疑点。'}]
    review_identity, _ = recovery.review_context(recovery.candidate(), {'status': 'NEEDS_REVIEW'}, {})
    recovery.record_review(pending, review_identity, {'issues': copy.deepcopy(pending)})
    assert digest(recovery.candidate()) != recovery.identity['base_hash'] == digest(original)
    return pipeline, plan, recovery


def test_http_guidance_after_accepted_patch_runs_formal_resume_and_preserves_binding(blocked, monkeypatch):
    service, pipeline, plan, client = blocked
    provider = pipeline.provider
    saved = state(pipeline)
    assert saved['applied_rounds'] == 1 and saved['unit_applied_counts'] == {'S01.U1': 1}
    before = within(pipeline.settings.workspace, saved['candidate_key'])
    assert digest(json.loads(before.read_bytes())) != saved['identity']['base_hash']
    state_path = pipeline.root / 'local-repair/S01.json'
    bound_bytes = state_path.read_bytes()
    evidence_bytes = {dependency['key']: within(pipeline.settings.workspace, dependency['key']).read_bytes()
                      for dependency in saved['evidence_dependencies']}
    pending = copy.deepcopy(saved['pending_issues'])
    approval = copy.deepcopy(service.store.get_run(pipeline.run['id'])['approval'])
    data = payload(blocked)
    response = client.post('/api/runs/' + pipeline.run['id'] + '/repair-guidance', json=data)
    assert response.status_code == 202, response.text
    action = events(pipeline, 'repair.guidance_requested')[0]
    assert action['recovery_binding']['state_sha256'] == digest(bound_bytes)
    assert state_path.read_bytes() == bound_bytes
    contexts, compiled = [], []
    generate = provider.generate
    def capture(role, context, schema):
        if role == 'repair_local_patch':
            contexts.append(copy.deepcopy(context))
        return generate(role, context, schema)
    provider.generate = capture
    def compile_section(self, source, entry, build):
        build.mkdir()
        compiled.append((source / entry).read_bytes())
        return {'status': 'PASS', 'issues': [], 'passes': 2, 'fixture': 'OFFLINE_GUIDANCE_COMPILER'}
    monkeypatch.setattr(Pipeline, 'compile', compile_section)
    resumed = Pipeline(pipeline.settings, service.store, service.store.claim('formal-guidance-accepted'))
    resumed.provider = provider
    resumed.run['input']['provider'] = 'live'
    completed, _ = resumed.lecture(plan)
    assert completed and len(compiled) == 1
    assert provider.writes == 1 and provider.patches == 2
    assert len(contexts) == 1 and contexts[0]['issues'] == pending
    assert contexts[0]['allowed_unit_ids'] == ['S01.U1']
    assert contexts[0]['repair_guidance']['action_id'] == data['action_id']
    after = state(resumed)
    assert after['identity'] == saved['identity']
    assert after['applied_rounds'] == after['proposal_calls'] == 2
    assert after['rejected_proposals'] == saved['rejected_proposals']
    assert after['unit_applied_counts'] == {'S01.U1': 2}
    assert after['phase'] == 'CHECKED' and not after['pending_issues']
    assert (guidance._folder(resumed, action) / 'recovery-before.json').read_bytes() == bound_bytes
    assert all(within(resumed.settings.workspace, key).read_bytes() == value for key, value in evidence_bytes.items())
    assert all(dependency in after['evidence_dependencies'] for dependency in saved['evidence_dependencies'])
    run = service.store.get_run(pipeline.run['id'])
    assert run['request_count'] == 17 and run['approval'] == approval and not run['reviews']
    assert len(events(resumed, 'repair.guidance_applied')) == 1


def test_loading_same_accepted_candidate_keeps_state_bytes_and_all_existing_counters(tmp_path):
    pipeline, plan, recovery = accepted_recovery(tmp_path, rounds=2)
    before = recovery.path.read_bytes()
    saved = copy.deepcopy(recovery.state)
    candidate = recovery.candidate()
    draft = pipeline.build_root / 'formal-accepted-seed'
    draft.mkdir()
    restored = LocalRecovery(pipeline, recovery.spec, {'synthetic': 'context'}, candidate, plan, draft, forced=True)
    assert restored.path.read_bytes() == before
    assert restored.identity == saved['identity'] and restored.state == saved
    assert restored.candidate() == candidate
    assert restored.state['proposal_calls'] == restored.state['applied_rounds'] == 2
    assert restored.state['unit_applied_counts'] == {'S01.U1': 2}
    assert restored.state['pending_issues'] and len(restored.state['evidence_dependencies']) == 2


@pytest.mark.parametrize('change', ['context', 'candidate'])
def test_changed_context_or_new_forced_body_rebases_and_refuses_stale_guidance(tmp_path, change):
    pipeline, plan, recovery = accepted_recovery(tmp_path)
    provider = Provider()
    resumed, action = request_and_resume(pipeline, plan, provider)
    saved = copy.deepcopy(recovery.state)
    context = {'synthetic': 'changed-context' if change == 'context' else 'context'}
    candidate = recovery.candidate()
    if change == 'candidate':
        candidate['units'][0]['tex'] += ' 外部新候选的额外正文。'
    draft = resumed.build_root / ('changed-' + change)
    draft.mkdir()
    restored = LocalRecovery(resumed, recovery.spec, context, candidate, plan, draft, forced=True)
    assert restored.state['phase'] == 'UNCHECKED_FORCED'
    assert digest(restored.path.read_bytes()) != action['recovery_binding']['state_sha256']
    assert restored.state['pending_issues'] == saved['pending_issues']
    for key in ('proposal_calls', 'applied_rounds', 'unit_applied_counts', 'evidence_dependencies'):
        assert restored.state[key] == saved[key]
    assert restored.identity['context_hash'] == digest(context)
    assert restored.identity['base_hash'] == digest(candidate)
    with pytest.raises(AgentError) as error:
        guidance.apply_requested_guidance(resumed, plan, restored.spec, candidate, restored, draft)
    assert error.value.code == 'REPAIR_GUIDANCE_CONFLICT'
    assert provider.patches == 0 and not events(resumed, 'repair.guidance_applied')


def test_accepted_seed_does_not_skip_old_proposal_evidence_verification(tmp_path):
    pipeline, plan, recovery = accepted_recovery(tmp_path)
    candidate = recovery.candidate()
    saved_bytes = recovery.path.read_bytes()
    dependency = recovery.state['evidence_dependencies'][0]
    within(pipeline.settings.workspace, dependency['key']).write_bytes(b'{}')
    draft = pipeline.build_root / 'damaged-proposal-seed'
    draft.mkdir()
    with pytest.raises(AgentError) as error:
        LocalRecovery(pipeline, recovery.spec, {'synthetic': 'context'}, candidate, plan, draft, forced=True)
    assert error.value.code == 'LOCAL_REPAIR_CACHE_INVALID'
    assert recovery.path.read_bytes() == saved_bytes
