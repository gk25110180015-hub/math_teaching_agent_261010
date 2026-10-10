import pytest

from math_agent.benchmark import CASES, comparison, page_metrics, request_metrics, unit_metrics


@pytest.mark.unit
def test_baseline_topics_follow_actual_three_reference_chapters():
    assert [(CASES[k]['directory'],CASES[k]['dataset']) for k in ('CH01','CH02','CH03')]==[('第一章','CH01'),('第二章','CH02'),('第三章','CH03')]
    assert '级数' in CASES['CH02']['topic'] and '函数极限' in CASES['CH03']['topic']
    assert CASES['smoke']['min_sections']==CASES['smoke']['max_sections']==2


@pytest.mark.unit
def test_structure_counts_exclude_hidden_scaffolding_but_do_not_judge_conditions():
    units=[{'id':'D','kind':'definition','raw_tex':r'对每个正实数 $\varepsilon>0$，存在整数 $N$。'},
        {'id':'E','kind':'exercise','raw_tex':'计算一个极限。'},
        {'id':'A','kind':'example_solution','raw_tex':'详细解答','semantic_relations':{'solution_of':'E'}},
        {'id':'P','kind':'property','raw_tex':'若单调且有界，则收敛。'},
        {'id':'H','kind':'theorem','source_visibility':'inactive','raw_tex':'隐藏内容'},
        {'id':'S','kind':'presentation_scaffold','raw_tex':'目录'}]
    result=unit_metrics(units,[{'id':'S1','title':'序列','prerequisites':[]}])
    assert result['unit_count']==4
    assert result['raw_kind_counts']['property']==1 and result['normalized_kind_counts']['theorem']==1
    assert result['condition_marker_counts']['existential_quantifier']==1
    assert result['exercise_strategy']['explicit_exercise_solution_links']==[{'solution':'A','exercise':'E'}]
    assert result['status']=='MEASURED' and 'correctness' not in result


@pytest.mark.unit
def test_density_uses_all_physical_pages_and_missing_pdf_is_not_zero():
    assert page_metrics(None)['page_count'] is None
    data={'status':'PASS','page_count':3,'pages':[{'physical_page':i,'sha256':str(i),'geometry':{'page_width_pt':720,'page_height_pt':720,'character_count':n,'image_count':0}} for i,n in enumerate((100,300,500),1)]}
    result=page_metrics(data)
    assert result['page_count']==3 and result['mean_characters_per_page']==300
    assert result['pages'][1]['characters']==300
    assert result['pages'][0]['characters_per_100cm2']==round(100/645.16*100,3)
    assert page_metrics({**data,'page_count':4})['status']=='PARTIAL'


@pytest.mark.unit
def test_provider_attempts_usage_missingness_and_schema_failure_stay_distinct():
    events=[{'sequence':1,'type':'provider.request','payload':{'role':'writer','attempt':1}},
        {'sequence':2,'type':'provider.result','payload':{'role':'writer','http_status':200,'elapsed_seconds':2.5}},
        {'sequence':3,'type':'provider.result','payload':{'role':'writer','usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}},
        {'sequence':4,'type':'provider.result','payload':{'role':'writer','validation_errors':[{'type':'missing'}]}},
        {'sequence':5,'type':'provider.request','payload':{'role':'writer','attempt':1}},
        {'sequence':6,'type':'provider.result','payload':{'role':'writer','status':'TIMEOUT','billing_uncertain':True}}]
    result=request_metrics(events,2,5)
    assert result['requests'][0]['status']=='SCHEMA_INVALID'
    assert result['requests'][1]['status']=='TIMEOUT' and result['requests'][1]['usage'] is None
    assert result['known_usage_sum']['total_tokens']==15 and not result['usage_reporting_complete']
    assert result['price'] is None and result['remaining_requests']==3


@pytest.mark.unit
def test_comparison_never_upgrades_counts_or_all_automated_passes_to_teacher_pass():
    original={'units':unit_metrics([{'id':'A','kind':'theorem','tex':'若条件A成立，结论B成立。'}]),'pdf':page_metrics(None)}
    generated={'units':unit_metrics([{'id':'B','kind':'definition','tex':'完全不同但未被数学工具判错的表述。'}]),'pdf':page_metrics(None)}
    quality={k:{'status':'PASS'} for k in ('content','math','compile','layout','policy','security')}
    result=comparison(original,generated,quality,{'decisions':[{'status':'NEEDS_REVIEW'}]})
    assert result['status']=='NEEDS_REVIEW' and result['teacher_visual_review']=='NOT_RUN'
    assert result['semantic_equivalence']=='NOT_ASSESSED'
    assert result['automated_quality_statuses']['math']=='PASS'
    assert result['decision_status_counts']=={'NEEDS_REVIEW':1}
    assert 'mathematical_error' not in str(result)


@pytest.mark.unit
def test_missing_quality_is_not_a_successful_comparison():
    item={'units':unit_metrics([]),'pdf':page_metrics(None)}
    result=comparison(item,item,None,None)
    assert set(result['automated_quality_statuses'].values())=={'NOT_RUN'}
    assert result['pages']=={'reference':None,'generated':None}


@pytest.mark.unit
def test_partial_usage_fields_remain_unknown_instead_of_zero():
    events=[{'sequence':1,'type':'provider.request','payload':{'role':'planner'}},
        {'sequence':2,'type':'provider.result','payload':{'role':'planner','usage':{'total_tokens':90}}}]
    result=request_metrics(events,1,3)
    assert result['known_usage_sum']=={'prompt_tokens':None,'completion_tokens':None,'total_tokens':90}
    assert not result['usage_reporting_complete']


@pytest.mark.unit
def test_driver_missing_env_cannot_create_a_live_run_or_fallback(tmp_path):
    from math_agent.benchmark import BenchmarkRunner
    from math_agent.settings import Settings
    from math_agent.util import AgentError
    runner=BenchmarkRunner(Settings(workspace=tmp_path/'w',live_api_enabled=False),tmp_path/'r')
    with pytest.raises(AgentError,match='enabled live API'):
        runner.run('smoke',execute_live=True)
    assert runner.service.list_runs()==[] and runner.state['cases']=={}


@pytest.mark.unit
def test_driver_records_real_selections_and_stops_before_teacher_review(tmp_path,monkeypatch):
    """Offline orchestration fixture: fake worker completion, real Service/SQLite."""
    from math_agent.benchmark import BenchmarkRunner
    from math_agent.settings import Settings
    from math_agent.pipeline import question
    from math_agent.worker import Worker
    from math_agent.store import Store
    from math_agent.domain import ReviewRequest
    from math_agent.util import AgentError
    def fake_tick(worker):
        store=Store(worker.settings.db_path)
        job=store.claim('offline-fixture')
        if job['kind']=='plan':
            plan={'title':'Offline fixture','sections':[{'id':'S1','title':'one'},{'id':'S2','title':'two'}],
                'theme':'default','lecture':{},'decisions':[],'decision_ids':[],
                'questions':[question(q,q,field,[(choice,choice,value)]) for q,choice,field,value in (
                    ('Q-PROOF','KEY','lecture.proof_policy','key'),('Q-EXAMPLE','BALANCED','lecture.example_focus','balanced'),
                    ('Q-EXERCISE','WITH','lecture.exercises','with_answers'),('Q-ANSWERS','END','lecture.answers_location','end'))],
                'unresolved_blocking_questions':['Q-PROOF','Q-EXAMPLE','Q-EXERCISE','Q-ANSWERS']}
            with store.transaction() as c: store.save_plan(c,job['run_id'],plan)
            store.finish(job,'AWAITING_PLAN_INPUT','plan.ready')
        else:
            store.finish(job,'AWAITING_USER_REVIEW','review.pages_and_quality')
        return True
    monkeypatch.setattr(Worker,'tick',fake_tick)
    runner=BenchmarkRunner(Settings(workspace=tmp_path/'w',live_api_enabled=False),tmp_path/'r')
    run=runner.execute_case('smoke')
    assert run['status']=='AWAITING_USER_REVIEW'
    assert run['input']['provider']=='live' and run['request_count']==0 # explicitly an offline fake worker
    assert run['plan']['lecture']['answers_location']=='end'
    assert all(d['actor']=='benchmark_driver' for d in run['plan']['decisions'])
    assert run['reviews']==[] and run['approval']['action_id'].startswith('benchmark_driver:smoke:')
    with pytest.raises(AgentError):
        runner.service.review(run['id'],ReviewRequest(artifact_id='none',sha256='0'*64,verdict='pass'))
    assert runner.execute_case('smoke')['id']==run['id'] # resume does not create a duplicate run


@pytest.mark.unit
def test_driver_budget_refuses_an_extra_request_before_worker_claim(tmp_path,monkeypatch):
    from math_agent.benchmark import BenchmarkRunner
    from math_agent.settings import Settings
    from math_agent.domain import NewRun
    from math_agent.worker import Worker
    import time
    runner=BenchmarkRunner(Settings(workspace=tmp_path/'w'),tmp_path/'r',per_run_budget=1,total_budget=1)
    run=runner.service.create(NewRun(workflow_id='lecture.generate',topic='offline',provider='live',trusted_input=True))
    runner.state['cases']['smoke']={'run_id':run['id'],'started_epoch':time.time()}
    with runner.service.store.transaction() as c:
        c.execute('UPDATE runs SET request_count=1 WHERE id=?',(run['id'],))
    monkeypatch.setattr(Worker,'tick',lambda self:pytest.fail('Budget exhausted before worker must be called'))
    assert runner.tick('smoke') is False
    assert runner.state['cases']['smoke']['driver_stop']=='TOTAL_REQUEST_BUDGET_EXHAUSTED'


@pytest.mark.unit
def test_driver_supplies_an_independent_hard_cap_for_its_remaining_total(tmp_path, monkeypatch):
    from math_agent.benchmark import BenchmarkRunner
    from math_agent.settings import Settings
    from math_agent.domain import NewRun
    from math_agent.worker import Worker
    import time
    runner=BenchmarkRunner(Settings(workspace=tmp_path/'w'),tmp_path/'r',per_run_budget=5,total_budget=4)
    run=runner.service.create(NewRun(workflow_id='lecture.generate',topic='offline',provider='live',trusted_input=True))
    runner.state['cases']['smoke']={'run_id':run['id'],'started_epoch':time.time()}
    with runner.service.store.transaction() as connection:
        connection.execute('UPDATE runs SET request_count=2 WHERE id=?',(run['id'],))
    observed=[]
    monkeypatch.setattr(Worker,'tick',lambda worker:observed.append((worker.settings.max_requests_per_run,
                                                                  worker.settings.request_budget_hard_cap)))
    assert runner.tick('smoke') is True
    assert observed==[(4,4)]
    assert runner.service.store.get_run(run['id'])['request_count']==2


@pytest.mark.unit
def test_failed_attempt_archive_is_immutable_across_report_updates(tmp_path):
    from math_agent.benchmark import BenchmarkRunner
    from math_agent.settings import Settings
    from math_agent.domain import NewRun
    from math_agent.util import digest
    import json,time
    runner=BenchmarkRunner(Settings(workspace=tmp_path/'w'),tmp_path/'r')
    run=runner.service.create(NewRun(workflow_id='lecture.generate',topic='offline',provider='live',trusted_input=True))
    runner.state['cases']['smoke']={'run_id':run['id'],'started_epoch':time.time()}
    run=runner.snapshot('smoke')
    report=tmp_path/'r/smoke/comparison.json'
    report.write_text('{"first_failure":"PLAN_DEPENDENCY"}',encoding='utf-8')
    original=report.read_bytes()
    archive=runner.preserve_attempt('smoke',run,'before-retry')
    report.write_text('{"new_outcome":"another attempt"}',encoding='utf-8')
    assert (archive/'comparison.json').read_bytes()==original
    manifest=json.loads((archive/'attempt_manifest.json').read_text(encoding='utf-8'))
    assert next(f for f in manifest['files'] if f['name']=='comparison.json')['sha256']==digest(original)
    assert manifest['teacher_visual_review']=='NOT_RUN'


@pytest.mark.unit
def test_pedagogical_diagnostics_expose_wrappers_and_empty_math_protocol_without_judging_math():
    from math_agent.benchmark import pedagogical_metrics
    section={'section_id':'S01','units':[
        {'id':'D','kind':'definition','tex':r'\begin{definition}正确量词\end{definition}'},
        {'id':'E','kind':'exercise','tex':'证明极限。'},
        {'id':'A','kind':'solution','tex':r'\begin{solution}数学上可能正确\end{solution}','relates_to':'E'}],
        'calculations':[]}
    result=pedagogical_metrics(section,{'id':'S01','required_kinds':['definition','exercise','solution']})
    assert result['structured_calculations']['status']=='NOT_RUN'
    assert result['render_wrapper_candidates']==[{'unit_id':'D','kind':'definition','environment':'definition'}, {'unit_id':'A','kind':'solution','environment':'solution'}]
    assert result['exercise_solution_links']==[{'exercise':'E','solution':'A'}]
    assert result['missing_planned_kinds']==[]
    assert result['mathematical_correctness']=='NOT_ASSESSED'


@pytest.mark.unit
def test_pedagogical_diagnostics_do_not_count_calculation_requests_as_proofs():
    from math_agent.benchmark import pedagogical_metrics
    section={'section_id':'S01','units':[{'id':'E','kind':'example','tex':'同一结果也可用其他方法证明。'}],
        'calculations':[{'id':'C1','unit_id':'E','kind':'limit','assumptions':{}}]}
    result=pedagogical_metrics(section,{'required_kinds':['proof']})
    assert result['structured_calculations']['status']=='REQUESTED_NOT_VERIFIED'
    assert result['structured_calculations']['requested_unit_ids']==['E']
    assert result['missing_planned_kinds']==['proof'] and result['mathematical_correctness']=='NOT_ASSESSED'
