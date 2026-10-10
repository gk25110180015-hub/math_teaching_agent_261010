"""Plan deletion and measured pagination; compiler mocks are explicitly local fixtures."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.beamer import render_beamer, coherent_modules
from math_agent.beamer_layout import build_measured_beamer
from math_agent.domain import NewRun, DecisionsRequest, RevisePlanRequest
from math_agent.parsing import parse_tex
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.worker import Worker


def plan_for(parsed):
    return {'title':'课堂','theme':'default','sections':parsed['sections'],'omissions':[],'additions':[]}


def test_saved_deletion_updates_executable_plan_and_can_restore_linked_answer(tmp_path):
    source = r'''\begin{document}\section{空节}原先的引入。
\section{计算}\begin{example}求 $1+1$。\end{example}
\begin{solution}$2$。\end{solution}\end{document}'''
    service = Service(Settings(workspace=tmp_path))
    run = service.create(NewRun(workflow_id='beamer.from_tex',topic='课堂',trusted_input=True))
    service.attachments(run['id'],'source.tex',source.encode())
    service.propose(run['id']); Worker(service.settings).tick()
    original = service.store.get_run(run['id'])
    units = original['input']['units']
    p = service.decisions(run['id'],DecisionsRequest(expected_plan_revision=original['plan']['revision'],omitted_unit_ids=[units[0]['id'],units[1]['id']]))
    assert p['sections'] == []
    assert len(p['omissions']) == 3  # statement also removes its associated answer
    assert len(p['empty_sections']) == 2
    assert len(p['source_sections']) == 2
    restored = service.decisions(run['id'],DecisionsRequest(expected_plan_revision=p['revision'],omitted_unit_ids=[units[0]['id']]))
    assert [s['title'] for s in restored['sections']] == ['计算']
    assert restored['sections'][0]['source_unit_ids'] == [units[1]['id'],units[2]['id']]
    renamed = service.revise(run['id'],RevisePlanRequest(expected_plan_revision=restored['revision'],section_titles={restored['sections'][0]['id']:'计算新标题'}))
    final = service.decisions(run['id'],DecisionsRequest(expected_plan_revision=renamed['revision'],omitted_unit_ids=[]))
    assert [s['title'] for s in final['sections']] == ['空节','计算新标题']
    assert service.store.get_run(run['id'])['input'] == original['input']


def test_renderer_prunes_empty_section_from_legacy_locked_plan_without_mutation(tmp_path):
    parsed=parse_tex(r'\begin{document}\section{应消失}删除正文。\section{保留}$x<1$\end{document}')
    p=plan_for(parsed);p['omissions']=[{'unit_id':parsed['units'][0]['id'],'kind':'user_authorized_omission','decision_id':'D1'}]
    original=copy.deepcopy(p)
    result=render_beamer(parsed,p,tmp_path)
    assert result['fidelity']['status']=='PASS'
    assert '应消失' not in (tmp_path/'slides.tex').read_text(encoding='utf-8')
    assert all(f['section_id']==p['sections'][1]['id'] for f in result['frame_plan'])
    assert p==original


@pytest.mark.parametrize('body',[
    '第一，讨论平均变化率。\n\n第二，讨论瞬时变化率。',
    r'先给出变化率的定义。\begin{definition}$m=\Delta y/\Delta x$。\end{definition}',
    r'\begin{theorem}$1+1=2$。\end{theorem}\begin{proof}由自然数加法。\end{proof}',
    r'\begin{example}求 $1+1$。\end{example}\begin{solution}$2$。\end{solution}\begin{remark}结果为整数。\end{remark}',
])
def test_measured_first_candidate_keeps_coherent_passages_together(tmp_path,body):
    parsed=parse_tex(r'\begin{document}\section{课堂}'+body+r'\end{document}')
    result=render_beamer(parsed,{**plan_for(parsed),'_layout':{'measured':True}},tmp_path)
    frames=[f for f in result['frame_plan'] if f['kind']=='content']
    assert len(frames)==1
    assert frames[0]['text_size']=='normalsize'
    assert result['fidelity']['status']=='PASS'
    if '\\begin{solution}' in body:
        assert '\\pause' in (tmp_path/'slides.tex').read_text(encoding='utf-8')


@pytest.mark.parametrize('needs_split',[False,True])
def test_only_overflowing_module_changes_and_fonts_precede_split(tmp_path,needs_split):
    parsed=parse_tex(r'\begin{document}\section{课堂}\begin{example}求 $1+1$。\end{example}\begin{solution}$2$。\end{solution}\begin{definition}$a<b$。\end{definition}\end{document}')
    calls=[]
    # Mock compiler: first coherent module overflows, unrelated definition always fits.
    def compile_mock(source,entry,build):
        text=(source/entry).read_text(encoding='utf-8')
        calls.append(text)
        fail=len(calls)<(4 if needs_split else 3)
        build.mkdir();log=build/'pass-2.tex.log'
        log.write_text('MATH-AGENT-FRAME-BEGIN F002\nOverfull \\vbox (2pt too high)\nMATH-AGENT-FRAME-END F002\n' if fail else '',encoding='utf-8')
        return {'status':'FAIL' if fail else 'PASS','pdf_path':None,'log_paths':[str(log)],'issues':[{'rule_id':'OVERFULL_BOX','severity':'blocking'}] if fail else []}
    source,rendered,fidelity,compiled,_=build_measured_beamer(parsed,plan_for(parsed),tmp_path,None,compile_mock,lambda *args:None)
    attempts=json.loads((tmp_path/'layout_candidates.json').read_text(encoding='utf-8'))
    assert len(calls)==(4 if needs_split else 3)
    assert attempts[0]['layout']['modules']=={}
    assert attempts[1]['layout']['modules']['U0001']=={'font_size':'small','split_long':False}
    assert attempts[2]['layout']['modules']['U0001']=={'font_size':'footnotesize','split_long':False}
    assert all('U0003' not in a['layout']['modules'] for a in attempts)
    assert all(f['text_size']=='normalsize' for f in rendered['frame_plan'] if f.get('module_id')=='U0003')
    assert fidelity['status']=='PASS'


def test_footer_geometry_risk_shrinks_locally_before_any_split(tmp_path,monkeypatch):
    parsed=parse_tex(r'\begin{document}\section{课堂}\begin{theorem}$a=a$。\end{theorem}\begin{proof}恒等式。\end{proof}\end{document}')
    calls=[]
    def compile_mock(source,entry,build):
        build.mkdir();pdf=build/'slides.pdf';pdf.write_bytes(b'mock-pdf')
        calls.append(source)
        return {'status':'PASS','pdf_path':str(pdf),'issues':[]}
    def inspect_mock(pdf,output,**kwargs):
        return {'status':'NEEDS_REVIEW','page_count':2,'pages':[],
                'overlay_map':{'pages':[{'physical_page':2,'frame_id':'F002'}]},
                'issues':[{'rule_id':'BODY_REGION_CONTACT','severity':'review','location':{'physical_page':2},
                           'evidence':[{'boundary':'footer'}]}] if len(calls)==1 else []}
    monkeypatch.setattr('math_agent.beamer_layout.inspect_pdf',inspect_mock)
    _,rendered,_,_,_=build_measured_beamer(parsed,plan_for(parsed),tmp_path,None,compile_mock,lambda *args:None)
    assert len(calls)==2
    content=[f for f in rendered['frame_plan'] if f['kind']=='content']
    assert len(content)==1 and content[0]['text_size']=='small'


def test_measured_module_cannot_override_allowed_fonts(tmp_path):
    parsed=parse_tex(r'\begin{document}$a<b$\end{document}')
    p={**plan_for(parsed),'_layout':{'measured':True,'modules':{'U0001':{'font_size':'tiny'}}}}
    with pytest.raises(ValueError,match='four permitted'):
        render_beamer(parsed,p,tmp_path)
