"""Actual SQLite/recheck state, synthetic bodies/artifacts; zero API/TeX calls."""
import copy
import json
import time

import pytest

from math_agent.benchmark import BenchmarkRunner, page_metrics, unit_metrics
from math_agent.domain import ExecuteRequest
from math_agent.util import canonical, digest, write_json
from test_teaching_quality_gate import TeachingProvider, teaching_setup

pytestmark = pytest.mark.unit
STAMP = '2026-01-01T00:00:00+00:00'


@pytest.fixture
def case(tmp_path, monkeypatch):
    service, pipeline, plan, _ = teaching_setup(tmp_path, monkeypatch, TeachingProvider(problem=False))
    runner = BenchmarkRunner(pipeline.settings, tmp_path/'reports')
    runner.state['cases']['CH02'] = {'run_id': pipeline.run['id'], 'started_epoch': time.time()}
    monkeypatch.setattr(runner, 'reference_metrics', lambda _: {
        'units': unit_metrics([]), 'pdf': page_metrics(None), 'fixture': 'SYNTHETIC_NO_REFERENCE_RENDER'})
    return service, pipeline, plan, runner


def checkpoint(case, sid, label, *, wrong_identity=False, legacy=False, correct_legacy_prefix=False):
    service, pipeline, plan, _ = case
    spec = next(s for s in plan['sections'] if s['id'] == sid)
    generated = {'section_id': sid, 'units': [{'id': sid+'.'+label, 'kind': 'explanation',
        'tex': 'Synthetic '+label, 'relates_to': None}], 'calculations': [],
        'calculation_limitations': [], 'uncertainties': []}
    source = pipeline.build_root/label/'source/lecture.tex'
    source.parent.mkdir(parents=True)
    source.write_text('SYNTHETIC NOT COMPILED '+label, encoding='utf-8')
    value = {'generated': generated, 'report': {},
        'source_key': source.relative_to(pipeline.settings.workspace).as_posix(),
        'source_hash': digest(source.read_bytes())}
    if not legacy:
        value['check_identity'] = pipeline._section_check_identity(plan, spec)
        if wrong_identity:
            value['check_identity']['plan_hash'] = 'another-approved-plan'
    key = pipeline._section_input_hash(plan,spec,[]) if correct_legacy_prefix else digest(label)
    with service.store.transaction() as connection:
        connection.execute('INSERT INTO steps VALUES(?,?,?,?,?,?)',
            (pipeline.run['id'], 'section.'+sid, key, canonical(value), digest(value), STAMP))
        rowid = connection.execute('SELECT last_insert_rowid()').fetchone()[0]
    return source, rowid, value


def artifacts(case, job, label, pages, quality='PASS'):
    service, pipeline, _, _ = case
    folder = pipeline.root/label
    folder.mkdir()
    payloads = {'lecture.pdf': b'SYNTHETIC_PDF_NOT_COMPILED',
        'quality_report.json': canonical({name:{'status':quality} for name in ('content','math','compile','layout','policy','security')}).encode(),
        'pdf_inspection.json': canonical({'status':'PASS','page_count':pages,'pages':[
            {'physical_page':n,'geometry':{'page_width_pt':600,'page_height_pt':800,'character_count':100,'image_count':0}}
            for n in range(1,pages+1)]}).encode()}
    rows=[]
    for name,raw in payloads.items():
        path=folder/name;path.write_bytes(raw)
        rows.append({'storage_key':path.relative_to(pipeline.settings.workspace).as_posix(),
            'name':name,'sha256':digest(raw),'media_type':'application/json' if name.endswith('.json') else 'application/pdf'})
    service.store.publish_artifacts(job,rows)
    return rows


def test_actual_recheck_supersedes_all_old_artifacts_without_reusing_their_passes(case):
    service,pipeline,plan,runner=case
    artifacts(case,pipeline.job,'old',8)
    before=runner.analyze('CH02')
    assert before['generated']['pdf']['page_count']==8
    service.store.finish(pipeline.job,'AWAITING_USER_REVIEW','review.pages_and_quality')
    service.recheck(pipeline.run['id'],ExecuteRequest(expected_plan_revision=plan['revision'],
        expected_plan_hash=plan['hash'],idempotency_key='offline-benchmark-recheck'))
    after=runner.analyze('CH02')
    assert after['generated']['pdf']['status']=='NOT_RUN'
    assert set(after['comparison']['automated_quality_statuses'].values())=={'NOT_RUN'}
    assert len(after['generated']['artifacts'])==3
    assert all(a['status']=='superseded' and a['revision']==plan['revision']
               and a['hash_check']=='PASS' and not a['selected_for_current'] for a in after['generated']['artifacts'])
    assert not after['generated']['artifact_selection']['current_artifact_ids']


def test_completed_recheck_selects_new_current_artifacts_and_retains_other_revision_history(case):
    service,pipeline,plan,runner=case
    artifacts(case,pipeline.job,'old-version',9)
    service.store.finish(pipeline.job,'AWAITING_USER_REVIEW','review.pages_and_quality')
    service.recheck(pipeline.run['id'],ExecuteRequest(expected_plan_revision=plan['revision'],
        expected_plan_hash=plan['hash'],idempotency_key='offline-benchmark-recheck'))
    job=service.store.claim('offline-recheck-worker')
    artifacts(case,job,'new-version',2,'NEEDS_REVIEW')
    older=artifacts(case,job,'another-revision',7,'FAIL')
    with service.store.transaction() as connection:
        for row in older:
            connection.execute('UPDATE artifacts SET revision=0 WHERE storage_key=?',(row['storage_key'],))
        connection.execute('UPDATE artifacts SET created_at=? WHERE run_id=?',(STAMP,pipeline.run['id']))
    result=runner.analyze('CH02')
    assert result['generated']['pdf']['page_count']==2
    assert result['comparison']['automated_quality_statuses']['math']=='NEEDS_REVIEW'
    history=result['generated']['artifacts']
    assert len(history)==9 and {a['revision'] for a in history}=={0,plan['revision']}
    assert sum(a['selected_for_current'] for a in history)==3
    assert all('new-version' in a['path'] for a in history if a['selected_for_current'])


def test_latest_same_timestamp_checkpoint_uses_rowid_skips_other_plan_and_outputs_plan_order(case):
    _,_,_,runner=case
    checkpoint(case,'S02','second-first')
    _,old,_=checkpoint(case,'S01','old')
    _,new,_=checkpoint(case,'S01','new')
    _,wrong,_=checkpoint(case,'S01','wrong-plan-newest',wrong_identity=True)
    result=runner.analyze('CH02')['generated']
    assert result['checked_section_count']==2
    selected=result['checkpoint_selection']['selected']
    assert [row['step_key'] for row in selected]==['section.S01','section.S02']
    assert selected[0]['checkpoint_rowid']==new>old
    assert [r['section_id'] for r in result['checked_section_pedagogy']]==['S01','S02']
    history=result['checkpoint_selection']['history']
    assert next(r for r in history if r['checkpoint_rowid']==wrong)['selection']=='OTHER_PLAN_SPEC_OR_MODEL'
    assert len(history)==4


@pytest.mark.parametrize('corrupt',['source','output_hash'])
def test_latest_eligible_corruption_never_falls_back_to_old_checked_body(case,corrupt):
    service,pipeline,_,runner=case
    checkpoint(case,'S01','older-valid')
    source,rowid,_=checkpoint(case,'S01','newer-broken')
    if corrupt=='source':source.write_text('ALTERED',encoding='utf-8')
    else:
        with service.store.transaction() as connection:
            connection.execute('UPDATE steps SET output_hash=? WHERE rowid=?',('bad-sha',rowid))
    result=runner.analyze('CH02')['generated']
    assert result['checked_section_count']==0
    assert result['checkpoint_selection']['status']=='BLOCKED_INVALID_CHECKPOINT'
    assert result['checkpoint_selection']['errors'][0]['checkpoint_rowid']==rowid
    assert len(result['checkpoint_selection']['history'])==2


def test_legacy_prefix_verification_is_read_only_and_does_not_create_pipeline_side_effects(case,monkeypatch):
    from math_agent.pipeline import Pipeline
    service,pipeline,_,runner=case
    checkpoint(case,'S01','legacy',legacy=True,correct_legacy_prefix=True)
    before=service.store.get_run(pipeline.run['id'])
    with service.store.connect() as connection:
        before_events=connection.execute('SELECT count(*) FROM events').fetchone()[0]
    monkeypatch.setattr(Pipeline,'__init__',lambda *a,**k:pytest.fail('Analysis cannot initialize Pipeline'))
    result=runner.analyze('CH02')['generated']
    assert result['checked_section_count']==1
    assert result['checkpoint_selection']['selected'][0]['input_matches_current_prefix']
    assert service.store.get_run(pipeline.run['id'])==before
    with service.store.connect() as connection:
        assert connection.execute('SELECT count(*) FROM events').fetchone()[0]==before_events
    assert not (pipeline.root/'section-checkpoint-snapshots').exists()


def test_missing_current_approval_never_counts_matching_old_bodies_or_artifacts(case):
    service,pipeline,_,runner=case
    checkpoint(case,'S01','approved-once')
    artifacts(case,pipeline.job,'once-current',3)
    with service.store.transaction() as connection:
        connection.execute('DELETE FROM approvals WHERE run_id=?',(pipeline.run['id'],))
    result=runner.analyze('CH02')['generated']
    assert result['checked_section_count']==0 and result['pdf']['status']=='NOT_RUN'
    assert result['checkpoint_selection']['status']=='NO_CURRENT_APPROVED_PLAN'
    assert len(result['artifacts'])==3 and all(not a['selected_for_current'] for a in result['artifacts'])


def test_bad_new_current_document_does_not_fall_back_to_older_valid_document(case):
    _,pipeline,_,runner=case
    artifacts(case,pipeline.job,'first-active',3)
    newest=artifacts(case,pipeline.job,'second-active',4)
    path=pipeline.settings.workspace/next(r['storage_key'] for r in newest if r['name']=='pdf_inspection.json')
    path.write_bytes(b'{"tampered":true}')
    result=runner.analyze('CH02')['generated']
    assert result['pdf']['status']=='NOT_RUN'
    selected=next(a for a in result['artifacts'] if a['name']=='pdf_inspection.json' and a['selected_for_current'])
    assert selected['hash_check']=='FAIL' and 'second-active' in selected['path']
