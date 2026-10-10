"""Offline provider/compile fixtures; these do not claim live API or XeLaTeX success."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.domain import NewRun,ConfirmRequest,ExecuteRequest
from math_agent.pipeline import Pipeline
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import AgentError,digest


class OfflineProvider:
    def __init__(self, fail_review=False):
        self.writer_calls=0
        self.review_calls=0
        self.fail_review=fail_review

    def generate(self,role,context,schema):
        if role=='writer_lecture_section':
            self.writer_calls+=1
            return {'section_id':'S01','units':[{'id':'S01-U01','kind':'definition',
                'tex':r'\begin{definition}实数列按正整数下标排列。\end{definition}','relates_to':None}],
                'calculations':[],'uncertainties':[]}
        assert role=='reviewer_math'
        if context.get('scope',{}).get('kind')=='chapter_coverage':
            return {'issues':[],'checked_unit_ids':[u['id'] for u in context['units']],
                    'limitations':['Neutral whole-chapter fixture; local recovery counters below remain local only.']}
        self.review_calls+=1
        if self.fail_review:
            self.fail_review=False
            raise AgentError('PROVIDER_TIMEOUT','Offline synthetic reviewer timeout')
        return {'issues':[],'checked_unit_ids':[u['id'] for u in context['units']],
            'limitations':['Offline synthetic reviewer; not a mathematical acceptance.']}


def setup_pipeline(tmp_path,provider,**settings_kwargs):
    settings=Settings(workspace=tmp_path/'w',reference_root=tmp_path/'references',**settings_kwargs)
    service=Service(settings)
    run=service.create(NewRun(workflow_id='lecture.generate',topic='Unrelated synthetic topic',trusted_input=True))
    plan={'title':'Offline draft recovery','provider':'mock','difficulty':'synthetic','theme':'default',
        'sections':[{'id':'S01','title':'Definition','objectives':['Explain a sequence'],
            'required_kinds':['definition'],'prerequisites':[],'reference_labels':[]}],
        'lecture':{'proof_policy':'key','exercises':'none','answers_location':'end'},
        'questions':[],'unresolved_blocking_questions':[],'decisions':[],'decision_ids':[]}
    with service.store.transaction() as c:service.store.save_plan(c,run['id'],plan)
    plan=service.store.get_run(run['id'])['plan']
    service.confirm(run['id'],ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],action_id='offline-fixture'))
    service.execute(run['id'],ExecuteRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],idempotency_key='offline-fixture'))
    job=service.store.claim('offline-test')
    pipeline=Pipeline(settings,service.store,job)
    pipeline.provider=provider
    return service,pipeline,plan


@pytest.mark.unit
def test_reviewer_timeout_reuses_unchecked_writer_but_reruns_normalize_math_review_compile(tmp_path,monkeypatch):
    from math_agent import mathcheck,lecture_fragments
    provider=OfflineProvider(fail_review=True)
    service,pipeline,plan=setup_pipeline(tmp_path,provider)
    calls={'normalize':0,'math':0,'compile':0}
    original_normalize=lecture_fragments.normalize_written_section
    original_math=mathcheck.check_math
    def normalize(data):
        calls['normalize']+=1
        return original_normalize(data)
    def math(data):
        calls['math']+=1
        return original_math(data)
    def compile(self,source,entry,build):
        calls['compile']+=1
        build.mkdir()
        return {'status':'PASS','issues':[],'passes':2,'page_count':1,'pdf_path':None,'fixture':'OFFLINE_FAKE_COMPILER'}
    monkeypatch.setattr(lecture_fragments,'normalize_written_section',normalize)
    monkeypatch.setattr(mathcheck,'check_math',math)
    monkeypatch.setattr(Pipeline,'compile',compile)
    with pytest.raises(AgentError,match='reviewer timeout'):
        pipeline.lecture(plan)
    original_candidate=next(pipeline.build_root.glob('sS01*/candidate.json'))
    original_hash=digest(original_candidate.read_bytes())
    with service.store.connect() as c:assert c.execute('SELECT count(*) FROM steps').fetchone()[0]==0
    service.store.finish(pipeline.job,'FAILED','review.section.S01',{'code':'PROVIDER_TIMEOUT'})
    service.retry(pipeline.run['id'])
    job=service.store.claim('offline-resumed')
    resumed=Pipeline(pipeline.settings,service.store,job)
    resumed.provider=provider
    completed,_=resumed.lecture(plan)
    assert provider.writer_calls==1 and provider.review_calls==2
    assert calls=={'normalize':2,'math':2,'compile':1}
    assert len(completed)==1 and digest(original_candidate.read_bytes())==original_hash
    assert len(list(resumed.build_root.glob('sS01*/candidate.json')))==2
    assert len(list(resumed.build_root.glob('sS01*/candidate-normalization.json')))==2
    with service.store.connect() as c:
        assert c.execute('SELECT count(*) FROM steps').fetchone()[0]==1
        assert c.execute("SELECT count(*) FROM events WHERE type='writer.draft_reused'").fetchone()[0]==0
    assert len(list(resumed.build_root.glob('sS01*/unchecked-local-recheck.json')))==1
    # Only the ordinary completed section checkpoint may skip subsequent checks.
    resumed.lecture(plan)
    assert calls=={'normalize':2,'math':2,'compile':1}
    assert provider.writer_calls==1 and provider.review_calls==2


@pytest.mark.unit
@pytest.mark.parametrize('change',['context','model','prompt','schema','candidate_hash','schema_payload','path_escape'])
def test_unchecked_cache_invalidates_on_every_relevant_change(tmp_path,monkeypatch,change):
    import math_agent.pipeline as module
    import math_agent.provider as provider_module
    provider=OfflineProvider()
    _,pipeline,plan=setup_pipeline(tmp_path,provider)
    spec=plan['sections'][0]
    context={'section':spec,'topic':'first'}
    _,first_dir=pipeline.writer_draft(spec,context)
    first_file=first_dir/'candidate.json'
    first_bytes=first_file.read_bytes()
    cache_path=pipeline.root/'draft-cache/S01.json'
    metadata=json.loads(cache_path.read_text(encoding='utf-8'))
    if change=='context':
        context={**context,'topic':'second'}
    elif change=='model':
        pipeline.settings=pipeline.settings.model_copy(update={'model':'different-offline-model'})
    elif change=='prompt':
        prompts=tmp_path/'prompts';prompts.mkdir()
        (prompts/'writer_lecture_section.md').write_text('Different controlled prompt',encoding='utf-8')
        monkeypatch.setattr(provider_module,'PROMPTS',prompts)
    elif change=='schema':
        class FutureSchema(module.WrittenSection):
            protocol_revision: int = 2
        monkeypatch.setattr(module,'WrittenSection',FutureSchema)
    elif change=='candidate_hash':
        first_file.write_text('{}',encoding='utf-8')
    elif change=='schema_payload':
        first_file.write_text('{"section_id":"S01","units":[]}',encoding='utf-8')
        metadata['candidate_hash']=digest(first_file.read_bytes())
        cache_path.write_text(json.dumps(metadata),encoding='utf-8')
    else:
        metadata['candidate_key']='../outside-candidate.json'
        cache_path.write_text(json.dumps(metadata),encoding='utf-8')
    _,second_dir=pipeline.writer_draft(spec,context)
    assert provider.writer_calls==2 and first_dir!=second_dir
    assert first_file.exists() and len(list((pipeline.root/'draft-cache/history').glob('*.json')))==1
    if change not in ('candidate_hash','schema_payload'):
        assert first_file.read_bytes()==first_bytes


@pytest.mark.unit
def test_reuse_keeps_only_unchecked_status_and_new_attempt_files(tmp_path):
    provider=OfflineProvider()
    _,pipeline,plan=setup_pipeline(tmp_path,provider)
    spec=plan['sections'][0];context={'section':spec}
    raw,first=pipeline.writer_draft(spec,context)
    candidate=copy.deepcopy(raw)
    raw['units'][0]['tex']='Changed in caller memory'
    second_raw,second=pipeline.writer_draft(spec,context)
    assert second_raw==candidate and second!=first and provider.writer_calls==1
    cache=json.loads((pipeline.root/'draft-cache/S01.json').read_text(encoding='utf-8'))
    assert cache['status']=='unchecked'
    evidence=json.loads((second/'draft-reuse.json').read_text(encoding='utf-8'))
    assert evidence['status']=='UNCHECKED_REUSED' and evidence['must_rerun_checks']
    assert not (first/'source').exists() and not (second/'source').exists()
