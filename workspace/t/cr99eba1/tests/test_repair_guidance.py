"""Offline guided repair with real SQLite/state files; models/compiler are injected."""
import copy
import json

import pytest

from math_agent import repair_guidance as guidance
from math_agent.pipeline import Pipeline
from math_agent.service import Service
from math_agent.util import AgentError, digest, write_json
from test_local_recovery import Provider, direct_recovery, setup, state


def request_and_resume(p, plan, provider, *, action_id='guide-1', changes=None):
    p.store.finish(p.job, 'BLOCKED', 'review.section.S01', {'code': 'UNCERTAINTY_DEPENDENCY_BLOCKED'})
    run = p.store.get_run(p.run['id'])
    ctx = guidance.guidance_context(p.settings, run)
    assert ctx
    action = {k: ctx[k] for k in ('section_id', 'candidate_hash', 'candidate_key', 'candidate_file_hash', 'recovery_binding')}
    action.update(action_id=action_id, payload_hash=digest(action_id), job_id=p.job['id'], plan_hash=plan['hash'],
        plan_revision=plan['revision'], unit_ids=['S01.U1'], instructions='仅在本单元明确既有定义与前提，并写出可独立核实的实际推理。',
        source='agent_audit', actor='local_user', request_count_preserved=run['request_count'], budget_version=1)
    action.update(changes or {})
    with p.store.transaction() as c:
        p.store.event(c, p.run['id'], 'repair.guidance_requested', action)
    Service(p.settings).retry(p.run['id'])
    resumed = Pipeline(p.settings, p.store, p.store.claim('guided-test'))
    resumed.provider = provider
    return resumed, action


def fixture(tmp_path, *, provider=None, global_state=False):
    p, plan, recovery = direct_recovery(tmp_path)
    provider = provider or Provider()
    review_identity = {'candidate_hash': digest(recovery.candidate()), 'plan_context_hash': recovery.identity['context_hash']}
    recovery.record_review([{'unit_id': 'S01.U1', 'severity': 'review', 'message': '原数学疑点保留。'}], review_identity, {'issues': []})
    saved_global = None
    if global_state:
        from math_agent.global_repair_contract import known_legacy_identity
        path = p.root / 'global-repairs' / 'r2' / 'before.json'
        write_json(path, recovery.candidate())
        saved_global = {'schema_version': 1, 'identity': known_legacy_identity(p, plan), 'rounds_used': 2,
            'phase': 'checking', 'pending': [], 'sections': {'S01': {'candidate_key': path.relative_to(p.settings.workspace).as_posix(),
            'candidate_hash': digest(path.read_bytes())}}, 'issues': [{'unit_id': 'S01.U1', 'message': '旧全局疑点'}],
            'round_directory': path.parent.relative_to(p.settings.workspace).as_posix()}
        p._save_global_repair_state(saved_global)
        saved_global = p._load_global_repair_state(plan)
        assert saved_global['schema_version'] == 2 and 'contract_migration' in saved_global
    p, action = request_and_resume(p, plan, provider)
    recovery.p = p
    guidance.prepare_guidance_resume(p, plan, saved_global)
    return p, plan, recovery, provider, action, saved_global


def apply(p, plan, recovery):
    return guidance.apply_requested_guidance(p, plan, recovery.spec, recovery.candidate(), recovery, recovery.draft)


def events(p, kind):
    with p.store.connect() as c:
        return [json.loads(row[0]) for row in c.execute('SELECT payload_json FROM events WHERE run_id=? AND type=?', (p.run['id'], kind))]


def test_target_patch_preserves_original_issues_approval_counters_and_other_unit(tmp_path):
    p, plan, r, provider, action, _ = fixture(tmp_path)
    before = r.candidate(); issues = copy.deepcopy(r.state['pending_issues'])
    approval = copy.deepcopy(p.store.get_run(p.run['id'])['approval'])
    result, normalization = apply(p, plan, r)
    assert normalization['status'] == 'PASS'
    assert result['units'][1] == before['units'][1] and result['units'][0] != before['units'][0]
    assert r.state['pending_issues'] == issues and r.state['phase'] == 'UNCHECKED_REPAIRED'
    assert r.state['unit_applied_counts'] == {'S01.U1': 1} and r.state['proposal_calls'] == 1
    assert p.store.get_run(p.run['id'])['approval'] == approval
    assert not p.store.get_run(p.run['id'])['reviews'] and provider.patches == 1
    assert len(events(p, 'repair.guidance_applied')) == 1
    assert apply(p, plan, r) is None and provider.patches == 1
    assert guidance.has_requested_guidance(p, plan, 'S01')  # Unchecked body may not use an old checkpoint.


@pytest.mark.parametrize('mode', ['scope', 'noop'])
def test_completed_bad_proposal_is_retained_and_never_rerolled(tmp_path, mode):
    p, plan, r, provider, action, _ = fixture(tmp_path, provider=Provider(bad=mode == 'scope', noop=mode == 'noop'))
    original = r.candidate()
    for _ in range(2):
        with pytest.raises(AgentError) as err: apply(p, plan, r)
        assert err.value.code == 'REPAIR_GUIDANCE_REJECTED'
    assert r.candidate() == original and provider.patches == 1 and r.state['rejected_proposals'] == 1
    assert r.state['pending_issues'] and not events(p, 'repair.guidance_applied')
    assert (guidance._folder(p, action) / 'proposal.json').exists()


@pytest.mark.parametrize('damage', ['body', 'review', 'state', 'target', 'plan'])
def test_wrong_bound_evidence_never_calls_model(tmp_path, damage):
    p, plan, r, provider, action, _ = fixture(tmp_path)
    if damage == 'body':
        r.state['candidate_hash'] = '0' * 64
    elif damage == 'review':
        (p.settings.workspace / r.state['last_review_key']).write_text('{}', encoding='utf-8')
    elif damage == 'state':
        r.state['pending_issues'].append({'unit_id': 'S01.U2', 'severity': 'review', 'message': '新增疑点'})
        r.save()
    elif damage == 'target':
        action['unit_ids'] = ['S01.U99']
    elif damage == 'plan':
        action['plan_hash'] = 'wrong-plan'
    if damage in ('target', 'plan'):
        with p.store.transaction() as c:
            c.execute("UPDATE events SET payload_json=? WHERE run_id=? AND type='repair.guidance_requested'", (json.dumps(action), p.run['id']))
    with pytest.raises(AgentError): apply(p, plan, r)
    assert provider.patches == 0


def test_budget_exhausted_before_proposal_preserves_original_state(tmp_path):
    p, plan, r, provider, action, _ = fixture(tmp_path)
    # Same limits mechanism used by normal local repairs, without any reset.
    p.effective_budget = lambda: {'local_repairs_per_unit': 0}
    with pytest.raises(AgentError) as err: apply(p, plan, r)
    assert err.value.code == 'BUDGET_EXHAUSTED'
    assert provider.patches == 0 and r.state['proposal_calls'] == 0 and r.state['pending_issues']


def test_cancelled_lease_rejects_before_any_model_call(tmp_path):
    p, plan, r, provider, action, _ = fixture(tmp_path)
    Service(p.settings).cancel(p.run['id'])
    with pytest.raises(AgentError) as err: apply(p, plan, r)
    assert err.value.code == 'LEASE_LOST' and provider.patches == 0


def test_transport_retry_reuses_counted_proposal_and_preserves_logs(tmp_path):
    provider = Provider(); original = provider.generate; calls = []
    def generate(role, ctx, schema):
        if role == 'repair_local_patch':
            calls.append(copy.deepcopy(ctx))
            if len(calls) == 1: raise AgentError('PROVIDER_TIMEOUT', 'mock transport failure')
        return original(role, ctx, schema)
    provider.generate = generate
    p, plan, r, _, action, _ = fixture(tmp_path, provider=provider)
    with pytest.raises(AgentError, match='mock transport failure'): apply(p, plan, r)
    assert r.state['proposal_calls'] == 1 and r.state['unit_applied_counts'] == {}
    result, _ = apply(p, plan, r)
    assert len(calls) == 2 and r.state['proposal_calls'] == 1 and r.state['unit_applied_counts'] == {'S01.U1': 1}
    assert result['units'][1]['tex'] == '本单元原样保留。'
    assert 'Not teacher approval' in calls[1]['repair_guidance']['authority']


def test_crash_after_accept_before_global_pointer_replays_without_second_patch(tmp_path, monkeypatch):
    p, plan, r, provider, action, global_state = fixture(tmp_path, global_state=True)
    before = copy.deepcopy(global_state); original_finish = guidance._finish_accepted
    def crash(*args, **kwargs):
        if args[4].get('guidance_acceptances'): raise RuntimeError('injected after-accept crash')
        return original_finish(*args, **kwargs)
    monkeypatch.setattr(guidance, '_finish_accepted', crash)
    with pytest.raises(RuntimeError, match='after-accept'): apply(p, plan, r)
    assert r.state['unit_applied_counts'] == {'S01.U1': 1} and global_state == before
    assert guidance._journal(p, action)['phase'] == 'APPLYING'
    monkeypatch.setattr(guidance, '_finish_accepted', original_finish)
    restored_global = json.loads((p.root / 'global-repair-state.json').read_bytes())
    guidance.prepare_guidance_resume(p, plan, restored_global)
    assert restored_global['rounds_used'] == 2 and restored_global['issues'] == before['issues']
    assert restored_global['phase'] == 'checking' and restored_global['sections'] != before['sections']
    assert p._global_repair_sections(restored_global)['S01'] == r.candidate()
    # Exercise the real next-load migration guard, not only the permissive reader.
    assert p._load_global_repair_state(plan) == restored_global
    assert guidance._journal(p, action)['phase'] == 'APPLIED' and provider.patches == 1
    assert apply(p, plan, r) is None and r.state['unit_applied_counts'] == {'S01.U1': 1}


def test_crash_after_applied_event_replays_one_event(tmp_path, monkeypatch):
    p, plan, r, provider, action, _ = fixture(tmp_path)
    save = guidance._save
    def crash(pipeline, act, journal):
        if journal['phase'] == 'APPLIED': raise RuntimeError('injected before-journal-final')
        return save(pipeline, act, journal)
    monkeypatch.setattr(guidance, '_save', crash)
    with pytest.raises(RuntimeError, match='before-journal-final'): apply(p, plan, r)
    assert len(events(p, 'repair.guidance_applied')) == 1
    monkeypatch.setattr(guidance, '_save', save)
    guidance.prepare_guidance_resume(p, plan, None)
    assert len(events(p, 'repair.guidance_applied')) == 1 and provider.patches == 1


def test_context_rejects_pending_global_action_or_tampered_candidate(tmp_path):
    p, plan, r, provider, action, global_state = fixture(tmp_path, global_state=True)
    p.store.finish(p.job, 'BLOCKED', 'review.section.S01', {'code': 'TEST'})
    run = p.store.get_run(p.run['id'])
    assert guidance.guidance_context(p.settings, run)
    global_state['pending'] = [{'section_id': 'S01'}]
    write_json(p.root / 'global-repair-state.json', global_state)
    assert guidance.guidance_context(p.settings, run) is None
    global_state['pending'] = []; write_json(p.root / 'global-repair-state.json', global_state)
    (p.settings.workspace / r.state['candidate_key']).write_text('{}', encoding='utf-8')
    assert guidance.guidance_context(p.settings, run) is None


def test_guided_changed_body_runs_math_review_compile_and_checkpoint_again(tmp_path, monkeypatch):
    from math_agent import mathcheck
    original_math = mathcheck.check_math; math_calls = []
    def checked(section):
        math_calls.append(copy.deepcopy(section)); return original_math(section)
    monkeypatch.setattr(mathcheck, 'check_math', checked)
    provider = Provider(); original = provider.generate; ordinary = []
    def generate(role, ctx, schema):
        if role == 'reviewer_math' and ctx.get('scope', {}).get('kind') != 'chapter_coverage':
            ordinary.append(copy.deepcopy(ctx))
            if len(ordinary) == 1: raise AgentError('PROVIDER_TIMEOUT', 'initial blocked fixture')
        return original(role, ctx, schema)
    provider.generate = generate
    service, p, plan, compiled = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError, match='initial blocked'): p.lecture(plan)
    # Real SQL approval/counter state; transport and compiler above are synthetic.
    p, action = request_and_resume(p, plan, provider)
    p.run['input']['provider'] = 'live'
    completed, reports = p.lecture(plan)
    assert provider.writes == 1 and provider.patches == 1 and len(ordinary) == 2 and len(compiled) == 1
    assert '已明示前提' in completed[0][1]['units'][0]['tex']
    assert state(p)['phase'] == 'CHECKED' and state(p)['unit_applied_counts'] == {'S01.U1': 1}
    assert len(math_calls) == 2 and '已明示前提' in math_calls[-1]['units'][0]['tex']
    # No calculations supplied: the bounded checker honestly retains its limitation.
    assert reports[0]['math']['status'] == 'NEEDS_REVIEW'
    assert not guidance.has_requested_guidance(p, plan, 'S01')
    assert not service.store.get_run(p.run['id'])['reviews']


def test_saved_proposal_hash_damage_blocks_without_reroll(tmp_path):
    p, plan, r, provider, action, _ = fixture(tmp_path, provider=Provider(noop=True))
    with pytest.raises(AgentError): apply(p, plan, r)
    (guidance._folder(p, action) / 'proposal.json').write_text('{}', encoding='utf-8')
    with pytest.raises(AgentError, match='SHA'): apply(p, plan, r)
    assert provider.patches == 1


def test_declared_doubt_is_retained_and_reassessed_only_after_changed_body(tmp_path, monkeypatch):
    from test_uncertainty_review import DoubtProvider, section
    provider = DoubtProvider(); original = provider.generate
    def generate(role, ctx, schema):
        if role == 'reviewer_uncertainty':
            provider.disposition = 'resolved_by_current_body' if '已明示前提' in ctx['section']['units'][0]['tex'] else 'open_dependency'
        return original(role, ctx, schema)
    provider.generate = generate
    service, p, plan, compiled = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError) as err: p.lecture(plan)
    assert err.value.code == 'UNCERTAINTY_DEPENDENCY_BLOCKED'
    p, action = request_and_resume(p, plan, provider); p.run['input']['provider'] = 'live'
    completed, reports = p.lecture(plan)
    assert completed[0][1]['uncertainties'] == section()['uncertainties']
    assert len(provider.doubt_calls) == 2 and provider.patches == 1 and len(compiled) == 1
    assert len(list((p.root / 'uncertainty-reviews').glob('*/state.json'))) == 2
    assert reports[0]['math']['status'] == 'NEEDS_REVIEW' and state(p)['phase'] == 'CHECKED'
    assert not service.store.get_run(p.run['id'])['reviews']


def test_same_guidance_does_not_bypass_independent_math_issue(tmp_path, monkeypatch):
    provider = Provider(); original = provider.generate; reads = []
    def generate(role, ctx, schema):
        if role == 'reviewer_math' and ctx.get('scope', {}).get('kind') != 'chapter_coverage':
            reads.append(ctx)
            if len(reads) == 1: raise AgentError('PROVIDER_TIMEOUT', 'fixture pause')
            return {'issues': [{'unit_id': 'S01.U1', 'severity': 'blocking', 'message': '独立数学错误未解决', 'evidence': 'mock proof evidence'}],
                    'checked_unit_ids': [u['id'] for u in ctx['units']], 'limitations': ['MOCK']}
        return original(role, ctx, schema)
    provider.generate = generate
    _, p, plan, compiled = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError, match='fixture pause'): p.lecture(plan)
    p, action = request_and_resume(p, plan, provider); p.run['input']['provider'] = 'live'
    with pytest.raises(AgentError) as err: p.lecture(plan)
    assert err.value.code == 'BUDGET_EXHAUSTED' and not compiled
    assert any('独立数学错误' in i['message'] for i in state(p)['pending_issues'])
    assert state(p)['unit_applied_counts'] == {'S01.U1': 2}


def test_late_provider_answer_cannot_accept_after_lease_loss(tmp_path):
    provider = Provider(); original = provider.generate
    p, plan, r, _, action, _ = fixture(tmp_path, provider=provider)
    before = r.candidate()
    def generate(role, ctx, schema):
        raw = original(role, ctx, schema)
        if role == 'repair_local_patch': Service(p.settings).cancel(p.run['id'])
        return raw
    provider.generate = generate
    with pytest.raises(AgentError) as err: apply(p, plan, r)
    assert err.value.code == 'LEASE_LOST' and r.candidate() == before
    assert r.state['unit_applied_counts'] == {} and not events(p, 'repair.guidance_applied')


def test_exact_global_and_local_binding_bytes_survive_initialization_crash_and_pointer_update(tmp_path, monkeypatch):
    p, plan, r, provider, action, global_state = fixture(tmp_path, global_state=True)
    binding = action['recovery_binding']
    global_before = (p.settings.workspace / binding['global_state_key']).read_bytes()
    local_before = (p.settings.workspace / binding['state_key']).read_bytes()
    original_save = guidance._save; interrupted = []
    def crash(pipeline, act, journal):
        if 'global-before.json' in journal['dependencies'] and not interrupted:
            interrupted.append(True)
            raise RuntimeError('snapshot-written-before-dependency-registered')
        return original_save(pipeline, act, journal)
    monkeypatch.setattr(guidance, '_save', crash)
    with pytest.raises(RuntimeError, match='snapshot-written'): apply(p, plan, r)
    assert provider.patches == 0 and r.state['proposal_calls'] == 0
    folder = guidance._folder(p, action)
    assert (folder / 'global-before.json').read_bytes() == global_before
    assert (folder / 'recovery-before.json').read_bytes() == local_before
    assert 'global-before.json' not in guidance._journal(p, action)['dependencies']
    monkeypatch.setattr(guidance, '_save', original_save)
    result, _ = apply(p, plan, r)
    journal = guidance._journal(p, action)
    assert provider.patches == 1 and journal['phase'] == 'APPLIED'
    assert journal['dependencies']['global-before.json'] == binding['global_state_sha256'] == digest(global_before)
    assert journal['dependencies']['recovery-before.json'] == binding['state_sha256'] == digest(local_before)
    assert (p.settings.workspace / binding['global_state_key']).read_bytes() != global_before
    assert (folder / 'global-before.json').read_bytes() == global_before
    assert (folder / 'recovery-before.json').read_bytes() == local_before
    assert p._global_repair_sections(p._load_global_repair_state(plan))['S01'] == result
