import json
from pathlib import Path
import pytest
from math_agent.beamer import render_beamer,check_fidelity
from math_agent.parsing import parse_tex
from math_agent.store import Store
from math_agent.settings import Settings, PROJECT_ROOT
from math_agent.util import AgentError, digest, uid
from math_agent.service import Service
from math_agent.domain import NewRun


def test_T46_formula_inequality_tampering_detected(tmp_path):
    source=r'\documentclass{ctexart}\begin{document}\section{不等式}条件为 $a<b$。\end{document}'
    parsed=parse_tex(source)
    plan={'title':'不等式','theme':'default','sections':parsed['sections'],'omissions':[],'additions':[]}
    rendered=render_beamer(parsed,plan,tmp_path)
    tex=(tmp_path/'slides.tex').read_text(encoding='utf-8')
    tampered=tex.replace('a<b','a>b')
    result=check_fidelity(parsed,{**plan,'_render_scaffold_hash':rendered['render_scaffold_hash']},tampered)
    assert result['status']=='FAIL'


def test_T08_model_omission_cannot_authorize_itself(tmp_path):
    parsed=parse_tex(r'\documentclass{ctexart}\begin{document}\section{证明}证明必须保留。\end{document}')
    plan={'title':'测试','theme':'default','sections':parsed['sections'],'omissions':[{'unit_id':parsed['units'][0]['id'],'category':'model_suggested_omission','approved':True}],'additions':[]}
    with pytest.raises(ValueError):render_beamer(parsed,plan,tmp_path)


def test_T57_request_budget_is_persistent(tmp_path):
    service=Service(Settings(workspace=tmp_path))
    run=service.create(NewRun(workflow_id='lecture.generate',topic='极限'))
    service.propose(run['id'])
    job=service.store.claim('budget-worker')
    service.store.count_request(job,1,{'test':'synthetic request'})
    with pytest.raises(AgentError) as exc:service.store.count_request(job,1,{'test':'must not call provider'})
    assert exc.value.code=='BUDGET_EXHAUSTED'
    assert Store(service.settings.db_path).get_run(run['id'])['request_count']==1


def test_T22_dependency_hash_invalidates_downstream_cache(tmp_path):
    service=Service(Settings(workspace=tmp_path))
    run=service.create(NewRun(workflow_id='lecture.generate',topic='极限'))
    service.propose(run['id']);job=service.store.claim('worker')
    before=digest(['locked-plan','S02',digest({'S01':'x>0'}),'writer-v1'])
    after=digest(['locked-plan','S02',digest({'S01':'x>=0'}),'writer-v1'])
    service.store.checkpoint(job,'section.S02',before,{'proof':'depends on strict positivity'})
    assert service.store.cached_step(run['id'],'section.S02',after) is None


def test_model_fragment_cannot_redefine_template():
    from math_agent.pipeline import Pipeline
    generated={'section_id':'S01','units':[{'id':'U1','kind':'explanation','tex':r'\renewcommand{\normalsize}{\tiny}正文','relates_to':None}]}
    issues=Pipeline.validate_written(None,{'id':'S01','required_kinds':[]},generated,{'lecture':{}})
    assert any(i['severity']=='blocking' and i.get('unit_id')=='U1' for i in issues)


def test_failure_diagnostic_is_downloadable_and_secret_free(tmp_path,monkeypatch):
    from math_agent.worker import Worker
    from math_agent.pipeline import Pipeline
    monkeypatch.setenv('MATH_AGENT_API_KEY','synthetic-runtime-failure-secret')
    def fail(self):raise RuntimeError('test failure synthetic-runtime-failure-secret')
    monkeypatch.setattr(Pipeline,'plan',fail)
    service=Service(Settings(workspace=tmp_path))
    run=service.create(NewRun(workflow_id='lecture.generate',topic='极限'))
    service.propose(run['id']);Worker(service.settings).tick()
    run=service.store.get_run(run['id'])
    assert run['status']=='FAILED'
    evidence=next(a for a in run['artifacts'] if a['name']=='failure_diagnostic.json')
    with service.store.connect() as c:
        path=tmp_path/c.execute('SELECT storage_key FROM artifacts WHERE artifact_id=?',(evidence['artifact_id'],)).fetchone()[0]
    text=path.read_text(encoding='utf-8')
    assert 'synthetic-runtime-failure-secret' not in text and '[REDACTED]' in text
    assert digest(path.read_bytes())==evidence['sha256']
    from fastapi.testclient import TestClient
    from math_agent.web.app import create_app
    with TestClient(create_app(service.settings),base_url='http://127.0.0.1:8765') as client:
        assert client.get('/api/session').status_code==200
        response=client.get('/api/artifacts/'+evidence['artifact_id'])
        assert response.status_code==200 and response.content==path.read_bytes()


@pytest.mark.reference
def test_T28_three_same_named_originals_and_all_hashes_unchanged():
    manifest=json.loads((PROJECT_ROOT/'reference_index'/'manifest.json').read_text(encoding='utf-8'))
    names={'CH01':'第一章','CH02':'第二章','CH03':'第三章'}
    lectures=[]
    for item in manifest['files']:
        path=PROJECT_ROOT.parent/names[item['dataset_id']]/item['relative_path']
        assert path.is_file()
        assert digest(path.read_bytes())==item['sha256'],str(path)
        if item['relative_path']=='大学数学（一）(1).tex':lectures.append(item)
    assert len(lectures)==3
    assert len({(x['dataset_id'],x['relative_path'],x['sha256']) for x in lectures})==3
