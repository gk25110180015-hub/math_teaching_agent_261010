"""Checkpoint contract regression: real SQLite, mock model, mock compiler only."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.pipeline import Pipeline
from math_agent.util import AgentError, digest, write_json
from test_global_repair import GlobalRepairProvider, setup


def change_reviewer_prompt(tmp_path, monkeypatch):
    from math_agent import provider
    folder = tmp_path / 'changed-prompts'
    folder.mkdir(exist_ok=True)
    for original in provider.PROMPTS.glob('*.md'):
        (folder / original.name).write_bytes(original.read_bytes())
    reviewer = folder / 'reviewer_math.md'
    reviewer.write_bytes(reviewer.read_bytes() + b'\nChanged reviewer contract fixture.\n')
    monkeypatch.setattr(provider, 'PROMPTS', folder)


def strip_contracts(pipeline):
    """Simulate legacy checkpoints while retaining verified original input hashes."""
    with pipeline.store.transaction() as connection:
        rows = connection.execute('SELECT * FROM steps WHERE run_id=?', (pipeline.run['id'],)).fetchall()
        for row in rows:
            output = json.loads(row['output_json'])
            output.pop('check_contract', None)
            output.pop('check_identity', None)
            connection.execute('UPDATE steps SET output_json=?,output_hash=? WHERE run_id=? AND step_key=?',
                (json.dumps(output), digest(output), pipeline.run['id'], row['step_key']))


@pytest.mark.unit
def test_same_contract_reuses_checkpoint_without_review_or_compile(tmp_path, monkeypatch):
    provider = GlobalRepairProvider()
    _, pipeline, plan, compiles = setup(tmp_path, provider, monkeypatch)
    first, _ = pipeline._lecture_sections(plan)
    second, _ = pipeline._lecture_sections(plan)
    assert first == second
    assert provider.writes == ['S01', 'S02']
    assert provider.locals == ['S01', 'S02'] and len(compiles) == 2


@pytest.mark.unit
@pytest.mark.parametrize('change', ['reviewer_prompt', 'legacy_contract'])
def test_changed_contract_rechecks_preserved_content_without_reauthoring(tmp_path, monkeypatch, change):
    provider = GlobalRepairProvider()
    service, pipeline, plan, compiles = setup(tmp_path, provider, monkeypatch)
    first, _ = pipeline._lecture_sections(plan)
    approved = copy.deepcopy(service.store.get_run(pipeline.run['id'])['approval'])
    state_path = pipeline.root / 'local-repair/S01.json'
    state = json.loads(state_path.read_bytes())
    state.update(applied_rounds=2, proposal_calls=3, rejected_proposals=1,
                 unit_applied_counts={'S01.U01': 2}, proposal_counts_by_key={'unit:S01.U01': 3},
                 rejected_counts_by_key={'unit:S01.U01': 1})
    write_json(state_path, state)
    if change == 'reviewer_prompt':
        change_reviewer_prompt(tmp_path, monkeypatch)
    else:
        strip_contracts(pipeline)
    second, _ = pipeline._lecture_sections(plan)
    assert second == first and provider.writes == ['S01', 'S02']
    assert provider.locals == ['S01', 'S02', 'S01', 'S02'] and len(compiles) == 4
    after = json.loads(state_path.read_bytes())
    for field in ('applied_rounds', 'proposal_calls', 'rejected_proposals', 'unit_applied_counts',
                  'proposal_counts_by_key', 'rejected_counts_by_key'):
        assert after[field] == state[field]
    assert service.store.get_run(pipeline.run['id'])['approval'] == approved
    with pipeline.store.connect() as connection:
        rows = connection.execute('SELECT output_json FROM steps WHERE run_id=?', (pipeline.run['id'],)).fetchall()
    assert all(json.loads(row[0]).get('check_contract') for row in rows)
    assert all(json.loads(row[0]).get('check_identity', {}).get('plan_hash') == plan['hash'] for row in rows)


@pytest.mark.unit
def test_legacy_verified_prefix_rechecks_downstream_after_upstream_changes(tmp_path, monkeypatch):
    provider = GlobalRepairProvider()
    _, pipeline, plan, compiles = setup(tmp_path, provider, monkeypatch)
    original, _ = pipeline._lecture_sections(plan)
    strip_contracts(pipeline)
    forced = copy.deepcopy(original[0][1])
    forced['units'][0]['tex'] += ' 这一已接受的前置假设必须保留。'
    rechecked = []
    completed, _ = pipeline._lecture_sections(plan, {'S01': forced},
        lambda sid, generated: rechecked.append((sid, copy.deepcopy(generated))))
    assert provider.writes == ['S01', 'S02']
    assert provider.locals == ['S01', 'S02', 'S01', 'S02'] and len(compiles) == 4
    assert completed[0][1] == forced and completed[1][1] == original[1][1]
    assert rechecked == [('S01', forced)]


@pytest.mark.unit
def test_refresh_restart_keeps_newest_accepted_local_candidate(tmp_path, monkeypatch):
    provider = GlobalRepairProvider()
    _, pipeline, plan, _ = setup(tmp_path, provider, monkeypatch)
    original, _ = pipeline._lecture_sections(plan)
    state_path = pipeline.root / 'local-repair/S01.json'
    state = json.loads(state_path.read_bytes())
    accepted = copy.deepcopy(original[0][1])
    accepted['units'][0]['tex'] += ' 已接受的局部修复必须保留。'
    candidate = pipeline.root / 'local-repair/S01/fixture-accepted.json'
    write_json(candidate, accepted)
    state.update(candidate_key=candidate.relative_to(pipeline.settings.workspace).as_posix(),
                 candidate_hash=digest(candidate.read_bytes()), phase='UNCHECKED_REPAIRED',
                 applied_rounds=1, proposal_calls=1, unit_applied_counts={'S01.U01': 1})
    write_json(state_path, state)
    change_reviewer_prompt(tmp_path, monkeypatch)
    completed, _ = pipeline._lecture_sections(plan)
    assert completed[0][1] == accepted and completed[1][1] == original[1][1]
    assert provider.writes == ['S01', 'S02']
    after = json.loads(state_path.read_bytes())
    assert after['applied_rounds'] == 1 and after['unit_applied_counts'] == {'S01.U01': 1}


@pytest.mark.unit
@pytest.mark.parametrize('corruption', ['checkpoint_hash', 'source_hash', 'source_outside_build'])
def test_refresh_does_not_accept_corrupt_or_uncontrolled_checkpoint(tmp_path, monkeypatch, corruption):
    provider = GlobalRepairProvider()
    _, pipeline, plan, _ = setup(tmp_path, provider, monkeypatch)
    pipeline._lecture_sections(plan)
    change_reviewer_prompt(tmp_path, monkeypatch)
    with pipeline.store.transaction() as connection:
        row = connection.execute('SELECT * FROM steps WHERE run_id=? AND step_key=?',
            (pipeline.run['id'], 'section.S01')).fetchone()
        output = json.loads(row['output_json'])
        if corruption == 'checkpoint_hash':
            connection.execute('UPDATE steps SET output_hash=? WHERE run_id=? AND step_key=?',
                ('corrupted', pipeline.run['id'], 'section.S01'))
        elif corruption == 'source_hash':
            (pipeline.settings.workspace / output['source_key']).write_bytes(b'corrupted')
        else:
            escaped = pipeline.settings.workspace / 'uncontrolled.tex'
            escaped.write_bytes((pipeline.settings.workspace / output['source_key']).read_bytes())
            output['source_key'] = escaped.relative_to(pipeline.settings.workspace).as_posix()
            connection.execute('UPDATE steps SET output_json=?,output_hash=? WHERE run_id=? AND step_key=?',
                (json.dumps(output), digest(output), pipeline.run['id'], 'section.S01'))
    with pytest.raises(AgentError) as error:
        pipeline._lecture_sections(plan)
    assert error.value.code == 'SECTION_CHECKPOINT_INVALID'
    assert provider.writes == ['S01', 'S02'] and provider.locals == ['S01', 'S02']


@pytest.mark.unit
def test_legacy_checkpoint_cannot_be_claimed_by_different_approved_plan(tmp_path, monkeypatch):
    provider = GlobalRepairProvider()
    _, pipeline, plan, _ = setup(tmp_path, provider, monkeypatch)
    pipeline._lecture_sections(plan)
    strip_contracts(pipeline)
    changed_plan = copy.deepcopy(plan)
    changed_plan['hash'] = 'different-approved-plan-fixture'
    changed_plan['sections'][0]['title'] = 'Changed learning objective'
    completed, _ = pipeline._lecture_sections(changed_plan)
    assert provider.writes == ['S01', 'S02', 'S01', 'S02']
    assert completed[0][0]['title'] == 'Changed learning objective'


@pytest.mark.unit
@pytest.mark.parametrize('checker_file', ['mathcheck.py', 'series_domain_text.py'])
def test_changed_math_checker_reopens_prior_pass_and_preserves_new_doubt(tmp_path, monkeypatch, checker_file):
    from math_agent import mathcheck
    provider = GlobalRepairProvider()
    _, pipeline, plan, compiles = setup(tmp_path, provider, monkeypatch)
    pipeline._lecture_sections(plan)
    original_read = Path.read_bytes
    original_is_file = Path.is_file
    checker_path = Path(mathcheck.__file__).with_name(checker_file).resolve()

    def changed_checker_source(path):
        if path.resolve() == checker_path:
            value = original_read(path) if original_is_file(path) else b''
            return value + b'\n# Updated check contract fixture\n'
        return original_read(path)

    def newly_detected_error(section):
        return {'schema_version': 1, 'status': 'FAIL', 'coverage': [u['id'] for u in section['units']],
                'evidence': [], 'limitations': [], 'issues': [{'rule_id': 'UPDATED_DOMAIN_CHECK',
                'severity': 'blocking', 'unit_id': section['units'][0]['id'],
                'message': 'The new deterministic checker found an undefined initial term.'}]}

    monkeypatch.setattr(Path, 'read_bytes', changed_checker_source)
    monkeypatch.setattr(Path, 'is_file', lambda path: path.resolve() == checker_path or original_is_file(path))
    monkeypatch.setattr(mathcheck, 'check_math', newly_detected_error)
    with pytest.raises(AgentError) as error:
        pipeline._lecture_sections(plan)
    assert error.value.code == 'MATH_REVIEW_BLOCKED'
    assert provider.writes == ['S01', 'S02'] and provider.locals == ['S01', 'S02', 'S01']
    assert len(compiles) == 2  # This new blocking mathematical error must stop before compile.
    state = json.loads((pipeline.root / 'local-repair/S01.json').read_bytes())
    assert state['phase'] == 'NEEDS_REPAIR'
    assert any(issue['rule_id'] == 'UPDATED_DOMAIN_CHECK' for issue in state['pending_issues'])


@pytest.mark.unit
@pytest.mark.parametrize('legacy', [False, True])
def test_changed_upstream_checkpoint_then_downstream_timeout_resumes_without_reauthoring(tmp_path, monkeypatch, legacy):
    provider = GlobalRepairProvider()
    service, pipeline, plan, compiles = setup(tmp_path, provider, monkeypatch)
    original, _ = pipeline._lecture_sections(plan)
    if legacy:
        strip_contracts(pipeline)
    forced = copy.deepcopy(original[0][1])
    forced['units'][0]['tex'] += ' 这是已接受的新前置假设。'
    provider.fail_following_once = True
    with pytest.raises(AgentError, match='following-section'):
        pipeline._lecture_sections(plan, {'S01': forced})
    service.store.finish(pipeline.job, 'FAILED', 'review.section.S02', {'code': 'PROVIDER_TIMEOUT'})
    service.retry(pipeline.run['id'])
    resumed = Pipeline(pipeline.settings, pipeline.store, pipeline.store.claim('offline-resumed-check'))
    resumed.provider = provider
    completed, _ = resumed._lecture_sections(plan)
    assert completed[0][1] == forced and completed[1][1] == original[1][1]
    assert provider.writes == ['S01', 'S02']
    assert provider.locals == ['S01', 'S02', 'S01', 'S02', 'S02'] and len(compiles) == 4
    assert service.store.get_run(pipeline.run['id'])['approval']['hash'] == plan['hash']
    if legacy:
        assert list((pipeline.root / 'section-checkpoint-snapshots').glob('*.json'))


@pytest.mark.unit
def test_corrupt_legacy_prefix_proof_cannot_authorize_seed_after_restart(tmp_path, monkeypatch):
    provider = GlobalRepairProvider()
    service, pipeline, plan, _ = setup(tmp_path, provider, monkeypatch)
    original, _ = pipeline._lecture_sections(plan)
    strip_contracts(pipeline)
    forced = copy.deepcopy(original[0][1])
    forced['units'][0]['tex'] += ' 修改前置假设。'
    provider.fail_following_once = True
    with pytest.raises(AgentError):
        pipeline._lecture_sections(plan, {'S01': forced})
    proof = next((pipeline.root / 'section-checkpoint-snapshots').glob('*.json'))
    proof.write_text('{"schema_version": 999}', encoding='utf-8')
    service.store.finish(pipeline.job, 'FAILED', 'review.section.S02', {'code': 'PROVIDER_TIMEOUT'})
    service.retry(pipeline.run['id'])
    resumed = Pipeline(pipeline.settings, pipeline.store, pipeline.store.claim('offline-resumed-check'))
    resumed.provider = provider
    counts = (len(provider.writes), len(provider.locals))
    with pytest.raises(AgentError) as error:
        resumed._lecture_sections(plan)
    assert error.value.code == 'SECTION_CHECKPOINT_INVALID'
    assert (len(provider.writes), len(provider.locals)) == counts


@pytest.mark.unit
@pytest.mark.parametrize('same_timestamp', [False, True])
@pytest.mark.parametrize('corrupt_newest', [None, 'output_hash', 'source_hash'])
def test_sqlite_checkpoint_versions_use_time_then_rowid_never_input_hash_order(tmp_path, monkeypatch, same_timestamp, corrupt_newest):
    from math_agent.pipeline import render_lecture
    provider = GlobalRepairProvider()
    _, pipeline, plan, _ = setup(tmp_path, provider, monkeypatch)
    pipeline._lecture_sections(plan)
    with pipeline.store.transaction() as connection:
        row = connection.execute('SELECT * FROM steps WHERE run_id=? AND step_key=?',
            (pipeline.run['id'], 'section.S01')).fetchone()
        newest = json.loads(row['output_json'])
        connection.execute('UPDATE steps SET input_hash=?,created_at=? WHERE run_id=? AND step_key=?',
            ('f'*64, '2020-01-01T00:00:00Z', pipeline.run['id'], 'section.S01'))
    newest['generated']['units'][0]['tex'] += ' 这是最新已接受版本。'
    folder = pipeline.build_root/'version-order-proof'
    folder.mkdir()
    source = folder/'lecture.tex'
    source.write_text(render_lecture(plan['title'], [(plan['sections'][0], newest['generated'])], plan), encoding='utf-8')
    newest.update(source_key=source.relative_to(pipeline.settings.workspace).as_posix(), source_hash=digest(source.read_bytes()))
    pipeline.store.checkpoint(pipeline.job, 'section.S01', '0'*64, newest)
    with pipeline.store.transaction() as connection:
        connection.execute('UPDATE steps SET created_at=? WHERE run_id=? AND step_key=? AND input_hash=?',
            ('2020-01-01T00:00:00Z' if same_timestamp else '2026-01-01T00:00:00Z', pipeline.run['id'], 'section.S01', '0'*64))
        if corrupt_newest == 'output_hash':
            connection.execute('UPDATE steps SET output_hash=? WHERE run_id=? AND step_key=? AND input_hash=?',
                ('corrupt', pipeline.run['id'], 'section.S01', '0'*64))
        elif corrupt_newest == 'source_hash':
            source.write_text('corrupt', encoding='utf-8')
        assert connection.execute('SELECT count(*) FROM steps WHERE run_id=? AND step_key=?',
            (pipeline.run['id'], 'section.S01')).fetchone()[0] == 2
    if corrupt_newest:
        with pytest.raises(AgentError) as error:
            pipeline._verified_section_checkpoints(plan)
        assert error.value.code == 'SECTION_CHECKPOINT_INVALID'
    else:
        snapshot = pipeline._verified_section_checkpoints(plan)['S01']
        assert snapshot['input_hash'] == '0'*64
        assert '最新已接受版本' in snapshot['output']['generated']['units'][0]['tex']
