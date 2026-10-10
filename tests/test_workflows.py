import json
import pytest
from math_agent.settings import Settings
from math_agent.service import Service
from math_agent.worker import Worker
from math_agent.domain import NewRun, DecisionsRequest, ConfirmRequest, ExecuteRequest


@pytest.mark.integration
def test_T02_T03_T60_plan_choices_persist(tmp_path):
    settings=Settings(workspace=tmp_path)
    service=Service(settings)
    run=service.create(NewRun(workflow_id='lecture.generate',topic='数列极限',trusted_input=True))
    service.propose(run['id'])
    Worker(settings).tick()
    run=service.store.get_run(run['id']);plan=run['plan']
    assert run['status']=='AWAITING_PLAN_INPUT'
    assert all(q['options'][-1]['id']=='CUSTOM' for q in plan['questions'])
    choices=[{'question_id':q['id'],'question_revision':q['revision'],'selected_option_ids':[q['options'][0]['id']]} for q in plan['questions']]
    plan=service.decisions(run['id'],DecisionsRequest(expected_plan_revision=plan['revision'],decisions=choices))
    before=plan['lecture']['example_focus']
    plan=service.decisions(run['id'],DecisionsRequest(expected_plan_revision=plan['revision'],decisions=[{'question_id':'Q-PROOF','question_revision':1,'selected_option_ids':['ALL']}]))
    assert plan['lecture']['proof_policy']=='all' and plan['lecture']['example_focus']==before
    assert plan['diff'] and len(plan['decision_ids'])==4
    service.confirm(run['id'],ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],action_id='user-confirm'))
    assert service.store.get_run(run['id'])['status']=='PLAN_CONFIRMED'


@pytest.mark.integration
def test_T06_actual_service_authorized_deletion(tmp_path):
    settings=Settings(workspace=tmp_path)
    service=Service(settings)
    run=service.create(NewRun(workflow_id='beamer.from_tex',trusted_input=True))
    text=r'''\documentclass{ctexart}
\newtheorem{example}{例题}
\begin{document}
\section{极限}
\begin{example}例 3：证明 $1/n\to0$。\end{example}
\textbf{解：}取 $N>1/\varepsilon$ 即可。
\section{保留}
保留这个公式 $a<b$。
\end{document}'''
    run=service.attachments(run['id'],'中文 (讲义).tex',text.encode())
    service.propose(run['id']);Worker(settings).tick()
    run=service.store.get_run(run['id']);plan=run['plan']
    target=next(u for u in run['input']['units'] if u['kind']=='example_statement')
    plan=service.decisions(run['id'],DecisionsRequest(expected_plan_revision=plan['revision'],omitted_unit_ids=[target['id']]))
    assert all(o['category']=='user_authorized_omission' and o['decision_id'] for o in plan['omissions'])
    assert len(plan['omissions'])==2
    service.confirm(run['id'],ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],action_id='delete-confirm'))
    assert service.store.get_run(run['id'])['approval']['hash']==plan['hash']


@pytest.mark.windows_compile
@pytest.mark.integration
def test_mock_lecture_full_checkpoint_compile_preview(tmp_path):
    settings=Settings(workspace=tmp_path)
    service=Service(settings); worker=Worker(settings)
    run=service.create(NewRun(workflow_id='lecture.generate',topic='数列极限',trusted_input=True))
    rid=run['id'];service.propose(rid);worker.tick()
    plan=service.store.get_run(rid)['plan']
    selections=[{'question_id':q['id'],'question_revision':q['revision'],'selected_option_ids':[q['options'][0]['id']]} for q in plan['questions']]
    plan=service.decisions(rid,DecisionsRequest(expected_plan_revision=plan['revision'],decisions=selections))
    service.confirm(rid,ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],action_id='test-confirm'))
    service.execute(rid,ExecuteRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],idempotency_key='test-build'))
    worker.tick();run=service.store.get_run(rid)
    assert run['status']=='AWAITING_USER_REVIEW',run.get('error')
    names={a['name'] for a in run['artifacts']}
    assert {'lecture.tex','lecture.pdf','source_bundle.zip','quality_report.json','decision_coverage.json'}.issubset(names)
    assert any(a['media_type']=='image/png' for a in run['artifacts'])
    assert run['approval']['hash']==plan['hash']
    with service.store.connect() as c:
        assert c.execute('SELECT count(*) FROM steps WHERE run_id=?',(rid,)).fetchone()[0]==2
    # A successful compile must not auto-authorize human visual review.
    assert not run['reviews']
