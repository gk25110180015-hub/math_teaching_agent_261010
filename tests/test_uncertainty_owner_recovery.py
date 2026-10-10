"""Offline, fail-closed metadata recovery for a saved null-owner resolution.

Only the redundant owner metadata may be removed from the captured completed
response; no new model answer, mathematical verdict, or patch authority is made.
"""
import copy
import json
import os
from pathlib import Path

import pytest

from math_agent.uncertainty_review import UncertaintyReview, declared_doubts, declared_issues, validate_uncertainty_assessment
from math_agent.util import AgentError, digest, within
from test_local_recovery import direct_recovery, setup, state
from test_uncertainty_independent_repair import IndependentProvider, sample_section


CAPTURE = Path(__file__).parent / 'fixtures' / 'uncertainty_least_squares_resolved'


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith(('MATH_AGENT_', 'OPENAI_', 'DEEPSEEK_')):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')


def captured(name):
    return json.loads((CAPTURE / name).read_bytes())


def saved_guard(tmp_path, *, response=None, context=None, failure_code=None):
    context = copy.deepcopy(context or captured('input.json'))
    response = copy.deepcopy(response or captured('response-1.json'))
    pipeline, _, _ = direct_recovery(tmp_path)
    calls = []
    class SavedProvider:
        def generate(self, role, ctx, schema):
            assert role == 'reviewer_uncertainty'
            calls.append(copy.deepcopy(ctx))
            if failure_code:
                raise AgentError(failure_code, 'Injected failure before any response')
            return copy.deepcopy(response)
    pipeline.provider = SavedProvider()
    guard = UncertaintyReview(pipeline, context)
    guard.ordinary_review(lambda _: copy.deepcopy(captured('ordinary-review.json')), {})
    with pytest.raises(AgentError):
        guard.evaluate()
    return guard, calls


def recover(guard):
    from math_agent.uncertainty_owner_recovery import recover_null_owner_resolution
    return recover_null_owner_resolution(guard)


def original_bytes(guard):
    return {path.name: path.read_bytes() for path in guard.folder.iterdir() if path.is_file()}


def test_real_saved_resolution_only_restores_null_metadata_without_model_or_patch(tmp_path):
    context = captured('input.json')
    raw = captured('response-1.json')
    assert context['declared_doubts'][0]['unit_id'] is None
    assert raw['items'][0]['unit_id'] == 'S01.U10'
    assert raw['items'][0]['disposition'] == 'resolved_by_current_body'
    assert not captured('ordinary-review.json')['issues']
    assert len([calculation for calculation in context['section']['calculations']
                if calculation['unit_id'] == 'S01.U10']) == 14
    with pytest.raises(ValueError, match='cannot guess or change'):
        validate_uncertainty_assessment(raw, context)
    guard, calls = saved_guard(tmp_path)
    before = original_bytes(guard)
    recovered = recover(guard)
    assert recovered is not None
    report, issues = recovered
    assert not issues
    normalized = copy.deepcopy(raw)
    normalized['items'][0]['unit_id'] = None
    assert report['assessment'] == validate_uncertainty_assessment(normalized, context)
    assert report['assessment']['items'][0]['repair_instruction'] is None
    assert report['assessment']['items'][0]['unit_id'] is None
    assert report['source_identity_hash'] == guard.key and report['identity_hash'] != guard.key
    assert report['teacher_review'] == 'NOT_RUN' and report['provider_calls_during_replay'] == 0
    assert report['evidence_sha256'] == digest(within(guard.p.settings.workspace, report['evidence_key']).read_bytes())
    assert guard.state['status'] == 'INVALID'
    assert len(calls) == 1
    assert all((guard.folder / name).read_bytes() == content for name, content in before.items())
    assert json.loads((guard.folder / 'response-1.json').read_bytes()) == raw
    assert recover(UncertaintyReview(guard.p, context)) == recovered
    assert len(calls) == 1
    # Original strict evaluator still rejects this body/response; the explicit
    # metadata recovery does not silently change its frozen judgment record.
    with pytest.raises(AgentError) as error:
        UncertaintyReview(guard.p, context).evaluate()
    assert error.value.code == 'UNCERTAINTY_REVIEW_BLOCKED'


@pytest.mark.parametrize('damage', [
    'open_actionable', 'open_dependency', 'remaining_dependency', 'repair_instruction',
    'prior_only', 'prior_extra', 'wrong_hash', 'wrong_quote', 'empty_evidence',
    'unknown_id', 'duplicate_id', 'located_owner_mismatch', 'multiple_owners',
    'owner_not_in_sources', 'wrong_evidence_owner', 'blank_reason',
])
def test_ineligible_or_invalid_saved_response_stays_blocked(tmp_path, damage):
    context, response = captured('input.json'), captured('response-1.json')
    item = response['items'][0]
    if damage == 'open_actionable':
        item['disposition'] = 'open_actionable'
        item['repair_instruction'] = '仅在已存在单元改写算式，离线测试不得视为新修复权限。'
    elif damage == 'open_dependency':
        item['disposition'] = 'open_dependency'
        item['remaining_dependency'] = True
    elif damage == 'remaining_dependency':
        item['remaining_dependency'] = True
    elif damage == 'repair_instruction':
        item['repair_instruction'] = '不得将带有修复指令的裁定转换为无条件通过。'
    elif damage in ('prior_only', 'prior_extra'):
        source = next(source for source in context['sources'] if source['source_key'] == 'current:S01.U10')
        prior = {**source, 'source_key': 'prior:S00.U01', 'unit_id': 'S00.U01'}
        context['sources'].append(prior)
        evidence = {'source_key': prior['source_key'], 'source_sha256': prior['source_sha256'], 'quote': prior['tex']}
        if damage == 'prior_only':
            item['evidence'] = [evidence]
        else:
            item['evidence'].append(evidence)
    elif damage == 'wrong_hash':
        item['evidence'][0]['source_sha256'] = '0' * 64
    elif damage == 'wrong_quote':
        item['evidence'][0]['quote'] = '不存在于所给正文中的虚构证明和分数结果。'
    elif damage == 'empty_evidence':
        item['evidence'] = []
    elif damage == 'unknown_id':
        item['uncertainty_id'] = 'D999-not-a-preserved-doubt'
    elif damage == 'duplicate_id':
        response['items'].append(copy.deepcopy(item))
    elif damage == 'located_owner_mismatch':
        context['section']['uncertainties'][0] = 'S01.U04 ' + context['section']['uncertainties'][0]
        context['declared_doubts'] = declared_doubts(context['section'])
        item['uncertainty_id'] = context['declared_doubts'][0]['uncertainty_id']
    elif damage in ('multiple_owners', 'wrong_evidence_owner'):
        source = next(source for source in context['sources'] if source['source_key'] == 'current:S01.U04')
        evidence = {'source_key': source['source_key'], 'source_sha256': source['source_sha256'], 'quote': source['tex']}
        if damage == 'multiple_owners':
            item['evidence'].append(evidence)
        else:
            item['evidence'] = [evidence]
    elif damage == 'owner_not_in_sources':
        item['unit_id'] = 'S01.U99'
    elif damage == 'blank_reason':
        item['reason'] = ' ' * 30
    guard, calls = saved_guard(tmp_path, response=response, context=context)
    before = original_bytes(guard)
    assert recover(guard) is None
    assert len(calls) == 1 and guard.state['status'] == 'INVALID'
    assert all((guard.folder / name).read_bytes() == content for name, content in before.items())
    with pytest.raises(AgentError) as error:
        guard.evaluate()
    assert error.value.code == 'UNCERTAINTY_REVIEW_BLOCKED'


@pytest.mark.parametrize('failure', ['INVALID_MODEL_JSON', 'PROVIDER_ALL_UNAVAILABLE'])
def test_no_completed_resolved_response_cannot_be_recovered(tmp_path, failure):
    guard, calls = saved_guard(tmp_path, failure_code=failure)
    before = original_bytes(guard)
    assert recover(guard) is None
    assert len(calls) == 1
    assert all((guard.folder / name).read_bytes() == content for name, content in before.items())


def test_fresh_guard_without_saved_invalid_result_is_read_only_and_not_recoverable(tmp_path):
    pipeline, _, _ = direct_recovery(tmp_path)
    guard = UncertaintyReview(pipeline, captured('input.json'))
    assert not guard.folder.exists()
    assert recover(guard) is None
    assert not guard.folder.exists()
    assert not (pipeline.root / 'uncertainty-owner-recovery').exists()


def test_pipeline_reuses_saved_owner_resolution_without_new_review_or_repair(tmp_path, monkeypatch):
    provider = IndependentProvider(issues=False, invalid_target='S01.U10')
    generate = provider.generate
    def resolved(role, context, schema):
        value = generate(role, context, schema)
        if role == 'reviewer_uncertainty':
            value['items'][0]['disposition'] = 'resolved_by_current_body'
            value['items'][0]['repair_instruction'] = None
        return value
    provider.generate = resolved
    service, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    approval = copy.deepcopy(service.store.get_run(pipeline.run['id'])['approval'])
    completed, reports = pipeline.lecture(plan)
    assert completed[0][1] == sample_section()
    assert len(compiled) == len(provider.ordinary) == len(provider.dispositions) == 1
    assert not provider.patches and provider.writes == 1
    assert reports[0]['uncertainty_review']['assessment']['items'][0]['unit_id'] is None
    assert not reports[0]['issues']
    assert state(pipeline)['unit_applied_counts'] == {} and state(pipeline)['proposal_calls'] == 0
    assert service.store.get_run(pipeline.run['id'])['approval'] == approval
    assert not service.store.get_run(pipeline.run['id'])['reviews']
    pipeline.lecture(plan)
    assert len(provider.dispositions) == 1 and not provider.patches


def test_other_unchanged_open_doubt_is_preserved_by_metadata_recovery(tmp_path):
    context, response = captured('input.json'), captured('response-1.json')
    context['section']['uncertainties'].append('另一条证明仍需独立依据，不能由本次算术核对消解。')
    context['declared_doubts'] = declared_doubts(context['section'])
    response['items'].append({'uncertainty_id': context['declared_doubts'][1]['uncertainty_id'],
        'unit_id': None, 'disposition': 'open_dependency', 'reason': '该独立证明仍然缺少可核验的依据，必须保留待核实状态。',
        'evidence': [], 'remaining_dependency': True, 'repair_instruction': None})
    guard, calls = saved_guard(tmp_path, context=context, response=response)
    report, issues = recover(guard)
    assert report['assessment']['items'][1] == response['items'][1]
    assert len(issues) == 1 and issues[0]['uncertainty_id'] == response['items'][1]['uncertainty_id']
    assert issues[0]['disposition'] == 'open_dependency' and len(calls) == 1


@pytest.mark.parametrize('damage', ['archive', 'missing_archive', 'event', 'source_response'])
def test_completed_recovery_evidence_damage_blocks_replay_without_model(tmp_path, damage):
    guard, calls = saved_guard(tmp_path)
    report, _ = recover(guard)
    archive = within(guard.p.settings.workspace, report['evidence_key'])
    if damage == 'archive':
        archive.write_bytes(b'{}')
    elif damage == 'missing_archive':
        archive.unlink()
    elif damage == 'source_response':
        (guard.folder / 'response-1.json').write_bytes(b'{}')
    else:
        with guard.p.store.transaction() as connection:
            connection.execute("UPDATE events SET payload_json=? WHERE run_id=? AND type='math.uncertainty_owner_recovered'",
                               (json.dumps({'source_identity_hash': guard.key, 'identity_hash': 'tampered'}), guard.p.run['id']))
    with pytest.raises(AgentError) as error:
        recover(UncertaintyReview(guard.p, guard.context))
    assert error.value.code == 'UNCERTAINTY_EVIDENCE_BLOCKED' and len(calls) == 1


@pytest.mark.parametrize('crash', ['after_archive', 'after_event'])
def test_interrupted_archive_or_receipt_recovers_once_without_changing_original_evidence(tmp_path, monkeypatch, crash):
    import math_agent.uncertainty_owner_recovery as module
    guard, calls = saved_guard(tmp_path)
    before = original_bytes(guard)
    original_write, original_event = module.write_json, guard.p.store.event
    if crash == 'after_archive':
        def interrupted_write(path, value):
            original_write(path, value)
            raise KeyboardInterrupt('Injected crash after immutable archive')
        monkeypatch.setattr(module, 'write_json', interrupted_write)
    else:
        def interrupted_event(connection, run_id, kind, value):
            original_event(connection, run_id, kind, value)
            if kind == 'math.uncertainty_owner_recovered':
                raise KeyboardInterrupt('Injected crash before receipt transaction commit')
        monkeypatch.setattr(guard.p.store, 'event', interrupted_event)
    with pytest.raises(KeyboardInterrupt):
        recover(guard)
    archive = guard.p.root / 'uncertainty-owner-recovery' / guard.key[:24] / 'recovery.json'
    saved_archive = archive.read_bytes()
    monkeypatch.setattr(module, 'write_json', original_write)
    monkeypatch.setattr(guard.p.store, 'event', original_event)
    for _ in range(2):
        report, issues = recover(UncertaintyReview(guard.p, guard.context))
        assert not issues and report['provider_calls_during_replay'] == 0
    assert archive.read_bytes() == saved_archive and len(calls) == 1
    assert all((guard.folder / name).read_bytes() == content for name, content in before.items())
    with guard.p.store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM events WHERE run_id=? AND type='math.uncertainty_owner_recovered'",
                                  (guard.p.run['id'],)).fetchone()[0] == 1


def resolved_provider(*, independent=False, tool_issue=False):
    provider = IndependentProvider(issues=independent, invalid_target='S01.U10')
    generate = provider.generate
    def generate_resolved(role, context, schema):
        value = generate(role, context, schema)
        if role == 'writer_lecture_section' and tool_issue:
            value['units'][2]['tex'] += ' S01.U10'
        if role == 'reviewer_uncertainty':
            value['items'][0]['disposition'] = 'resolved_by_current_body'
            value['items'][0]['repair_instruction'] = None
        return value
    provider.generate = generate_resolved
    return provider


def test_pipeline_restores_saved_invalid_pending_declaration_without_review_loop(tmp_path, monkeypatch):
    import math_agent.uncertainty_owner_recovery as module
    provider = resolved_provider()
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    original_recover = module.recover_null_owner_resolution
    monkeypatch.setattr(module, 'recover_null_owner_resolution', lambda guard: None)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'UNCERTAINTY_REVIEW_BLOCKED'
    assert state(pipeline)['pending_issues'] == declared_issues(sample_section())
    old_evidence = {path: path.read_bytes() for path in (pipeline.root / 'uncertainty-reviews').glob('*/*.json')}
    monkeypatch.setattr(module, 'recover_null_owner_resolution', original_recover)
    completed, reports = pipeline.lecture(plan)
    assert completed and len(compiled) == 1 and not reports[0]['issues']
    assert len(provider.ordinary) == len(provider.dispositions) == provider.writes == 1
    assert not provider.patches and not state(pipeline)['pending_issues']
    assert all(path.read_bytes() == raw for path, raw in old_evidence.items())


def test_recovered_owner_cannot_discharge_pending_declaration_from_other_guard_identity(tmp_path, monkeypatch):
    import math_agent.uncertainty_owner_recovery as module
    from math_agent.local_recovery import LocalRecovery
    provider = resolved_provider()
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    original_recover = module.recover_null_owner_resolution
    original_record = LocalRecovery.record_review
    monkeypatch.setattr(module, 'recover_null_owner_resolution', lambda guard: None)
    def other_origin(recovery, issues, identity, report):
        return original_record(recovery, issues, {**identity, 'uncertainty_identity': 'another-frozen-guard'}, report)
    monkeypatch.setattr(LocalRecovery, 'record_review', other_origin)
    with pytest.raises(AgentError):
        pipeline.lecture(plan)
    monkeypatch.setattr(module, 'recover_null_owner_resolution', original_recover)
    monkeypatch.setattr(LocalRecovery, 'record_review', original_record)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'REPAIR_SCOPE_UNCLEAR'
    assert state(pipeline)['pending_issues'] == declared_issues(sample_section())
    assert not compiled and not provider.patches


@pytest.mark.parametrize('retained', ['ordinary', 'tool', 'changed_message', 'extra_field'])
def test_pipeline_owner_recovery_never_erases_independent_or_nonidentical_doubt(tmp_path, monkeypatch, retained):
    import math_agent.uncertainty_owner_recovery as module
    from math_agent.local_recovery import LocalRecovery
    provider = resolved_provider(independent=retained == 'ordinary', tool_issue=retained == 'tool')
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider, max_local_repair_attempts=0)
    original_recover = module.recover_null_owner_resolution
    monkeypatch.setattr(module, 'recover_null_owner_resolution', lambda guard: None)
    original_record = LocalRecovery.record_review
    extra = None
    if retained in ('changed_message', 'extra_field'):
        extra = copy.deepcopy(declared_issues(sample_section())[0])
        if retained == 'changed_message':
            extra['message'] += ' 这是不同来源的独立审阅疑点，不能按编号清除。'
        else:
            extra['evidence'] = '独立来源的具体证据不能因文字相同而清除。'
        def with_independent_pending(recovery, issues, identity, report):
            return original_record(recovery, [*issues, copy.deepcopy(extra)], identity, report)
        monkeypatch.setattr(LocalRecovery, 'record_review', with_independent_pending)
    with pytest.raises(AgentError):
        pipeline.lecture(plan)
    saved = copy.deepcopy(state(pipeline)['pending_issues'])
    monkeypatch.setattr(LocalRecovery, 'record_review', original_record)
    monkeypatch.setattr(module, 'recover_null_owner_resolution', original_recover)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code in ('BUDGET_EXHAUSTED', 'REPAIR_SCOPE_UNCLEAR')
    assert not compiled and not provider.patches
    pending = state(pipeline)['pending_issues']
    if extra:
        assert extra in pending
    else:
        expected = [issue for issue in saved if issue.get('rule_id') != 'DECLARED_MATH_UNCERTAINTY']
        assert expected and all(issue in pending for issue in expected)
    assert len(provider.ordinary) == len(provider.dispositions) == 1


def test_owner_recovery_helper_is_part_of_section_check_contract(tmp_path, monkeypatch):
    import math_agent.uncertainty_owner_recovery as module
    pipeline, _, _ = direct_recovery(tmp_path)
    before = pipeline._section_check_contract()
    path = Path(module.__file__).resolve()
    raw = path.read_bytes()
    assert before['source_hashes'][path.name] == digest(raw)
    original_read = Path.read_bytes
    def changed_read(candidate):
        return raw + b'\n# injected changed helper contract\n' if candidate.resolve() == path else original_read(candidate)
    monkeypatch.setattr(Path, 'read_bytes', changed_read)
    after = pipeline._section_check_contract()
    assert after != before
    assert after['source_hashes'][path.name] != before['source_hashes'][path.name]
