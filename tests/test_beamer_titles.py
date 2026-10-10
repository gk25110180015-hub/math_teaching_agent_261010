import copy
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from math_agent.beamer import check_fidelity, render_beamer
from math_agent.beamer_layout import build_measured_beamer
from math_agent.beamer_titles import FrameTitle, generate_frame_titles, title_map
from math_agent.parsing import parse_tex
from math_agent.util import AgentError


SOURCE = r'''\begin{document}\section{导数及其应用}
\begin{definition}导数是差商的极限。\end{definition}
\begin{example}用导数符号判断 $x^3-3x$ 的单调区间。\end{example}
\end{document}'''


def test_titles_use_actual_frame_content_and_preserve_source_and_sections(tmp_path):
    parsed = parse_tex(SOURCE)
    plan = {'title':'导数','sections':parsed['sections'],'omissions':[],'additions':[]}
    original = copy.deepcopy(plan)
    requests = []
    def name(frames):
        requests.extend(frames)
        return {f['frame_id']: '差商与导数的定义' if '差商' in f['content_tex'] else '用导数判断单调区间' for f in frames}
    result = render_beamer(parsed, plan, tmp_path, title_generator=name)
    tex = (tmp_path/'slides.tex').read_text(encoding='utf-8')
    assert len(requests) == 2
    assert all(f['section_title']=='导数及其应用' for f in requests)
    assert [f['title'] for f in result['frame_plan']] == ['目录','差商与导数的定义','用导数判断单调区间']
    assert r'\section{导数及其应用}' in tex
    assert r'\begin{frame}[t,fragile]{差商与导数的定义}' in tex
    assert result['fidelity']['status'] == 'PASS' and plan == original
    changed = tex.replace('差商与导数的定义', '外部篡改标题')
    assert check_fidelity(parsed, {**plan,'_render_scaffold_hash':result['render_scaffold_hash']}, changed)['status']=='FAIL'


def test_addition_titles_are_escaped_and_measured_before_compilation(tmp_path):
    parsed = parse_tex(SOURCE)
    plan = {'title':'导数','sections':parsed['sections'],'additions':[
        {'id':'A1','decision_id':'D1','insertion_location':parsed['sections'][0]['id'],'new_content':'新增例题。'}]}
    def name(frames):
        assert any(f['kind']=='authorized_addition' and f['content_tex']=='新增例题。' for f in frames)
        return {f['frame_id']:'比较 10% 与 {x}' for f in frames}
    def compile_mock(source, entry, build):
        assert r'\begin{frame}[t,fragile]{比较 10\% 与 \{x\}}' in (source/entry).read_text(encoding='utf-8')
        return {'status':'PASS','pdf_path':None,'issues':[]}
    _, rendered, fidelity, _, _ = build_measured_beamer(parsed, plan, tmp_path, None, compile_mock, lambda *a:None, title_generator=name)
    assert fidelity['status']=='PASS'
    assert all(f.get('title_source')=='model' for f in rendered['frame_plan'] if f['kind']!='directory')


@pytest.mark.parametrize('titles', [[], [{'frame_id':'F002','title':'定义'}]*2, [{'frame_id':'F003','title':'定义'}]])
def test_title_response_must_match_the_requested_pages(titles):
    with pytest.raises(ValueError):
        title_map({'titles':titles}, [{'frame_id':'F002'}])


@pytest.mark.parametrize('title', [' ', '多行\n标题', '长'*33])
def test_title_length_and_plain_line_contract(title):
    with pytest.raises(ValueError):
        FrameTitle(frame_id='F002',title=title)


def title_pipeline(generate):
    saved = {}
    store = SimpleNamespace(cached_step=lambda rid,key,identity:saved.get((key,identity)),
        checkpoint=lambda job,key,identity,value:saved.update({(key,identity):value}),
        transaction=nullcontext, assert_fence=lambda *args:None)
    return SimpleNamespace(run={'id':'test','plan':{'hash':'approved','title':'导数'}}, job={}, store=store,
        settings=SimpleNamespace(max_schema_repair_attempts=1), stage=lambda *a:None,
        provider=SimpleNamespace(generate=generate))


def test_title_cache_tracks_page_content_not_changing_frame_numbers():
    calls = []
    def generate(role, context, schema):
        calls.append(copy.deepcopy(context))
        return {'titles':[{'frame_id':f['frame_id'],'title':'差商的极限'} for f in context['frames']]}
    pipeline = title_pipeline(generate)
    frame = {'frame_id':'F002','section_title':'导数','content_tex':'差商的极限。'}
    assert generate_frame_titles(pipeline,[frame]) == {'F002':'差商的极限'}
    assert generate_frame_titles(pipeline,[{**frame,'frame_id':'F005'}]) == {'F005':'差商的极限'}
    assert len(calls)==1
    generate_frame_titles(pipeline,[{**frame,'content_tex':'用差商求极限。'}])
    assert len(calls)==2


def test_missing_titles_are_repaired_and_never_silently_fallback_to_section():
    calls=[]
    def generate(role, context, schema):
        calls.append(copy.deepcopy(context))
        return {'titles':[{'frame_id':'wrong','title':'导数'}]}
    with pytest.raises(AgentError,match='逐页标题'):
        generate_frame_titles(title_pipeline(generate),[{'frame_id':'F002','content_tex':'差商'}])
    assert len(calls)==2 and calls[1]['repair_issues']


@pytest.mark.windows_compile
def test_worker_delivers_compiled_content_titles(tmp_path, monkeypatch):
    import json
    from math_agent.domain import NewRun, ConfirmRequest, ExecuteRequest
    from math_agent.provider import MockProvider
    from math_agent.service import Service
    from math_agent.settings import Settings
    from math_agent.worker import Worker
    settings = Settings(workspace=tmp_path,live_api_enabled=False)
    service = Service(settings)
    worker = Worker(settings)
    calls = []
    def generate(self, role, context, schema):
        assert role=='beamer_frame_titles'
        calls.append(context)
        return {'titles':[{'frame_id':f['frame_id'], 'title':'差商的极限定义' if '差商' in f['content_tex'] else '导数符号与单调性'}
                          for f in context['frames']]}
    monkeypatch.setattr(MockProvider,'generate',generate)
    rid = service.create(NewRun(workflow_id='beamer.from_tex',topic='导数课堂',trusted_input=True))['id']
    service.attachments(rid,'source.tex',SOURCE.encode('utf-8'))
    service.propose(rid); worker.tick()
    plan=service.get(rid)['plan']
    identity={'expected_plan_revision':plan['revision'],'expected_plan_hash':plan['hash']}
    service.confirm(rid,ConfirmRequest(**identity,action_id='test-title-confirm'))
    service.execute(rid,ExecuteRequest(**identity,idempotency_key='test-title-build')); worker.tick()
    run=service.store.get_run(rid)
    assert run['status']=='AWAITING_USER_REVIEW',run.get('error')
    with service.store.connect() as connection:
        artifacts={a['name']:tmp_path/a['storage_key'] for a in connection.execute(
            'SELECT name,storage_key FROM artifacts WHERE run_id=?',(rid,))}
    assert artifacts['slides.pdf'].is_file() and len(calls)==1
    frames=json.loads(artifacts['frame_plan.json'].read_text(encoding='utf-8'))
    assert [f['title'] for f in frames]==['目录','差商的极限定义','导数符号与单调性']
    quality=json.loads(artifacts['quality_report.json'].read_text(encoding='utf-8'))
    assert quality['compile']['status']==quality['fidelity']['status']=='PASS'
    assert run['approval']['hash']==plan['hash']
