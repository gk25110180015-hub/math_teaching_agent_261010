"""Relocated answers must link to the actual exercise counters across sections."""
import copy
import json
import os
from pathlib import Path
import re

import pytest

from math_agent.pipeline import render_lecture
from math_agent.util import AgentError,digest


def fixture():
    plan={'provider':'mock','lecture':{'answers_location':'end'}}
    sections=[({'id':'S01','title':'第一节'}, {'units':[
        {'id':'EX','kind':'example','tex':r'计算 $1+1$。','relates_to':None},
        {'id':'EX.A','kind':'solution','tex':r'例题原解 $1+1=2$。','relates_to':'EX'},
        {'id':'E1','kind':'exercise','tex':r'计算 $2+2$。','relates_to':None},
        {'id':'A1','kind':'solution','tex':r'第一节答案 $2+2=4$。','relates_to':'E1'},
    ]}),({'id':'S02','title':'第二节'}, {'units':[
        {'id':'E1','kind':'exercise','tex':r'计算 $3+3$。','relates_to':None},
        {'id':'A1','kind':'solution','tex':r'第二节答案 $3+3=6$。','relates_to':'E1'},
    ]})]
    return plan,sections


def test_end_answers_have_deterministic_distinct_exercise_links_and_unchanged_bodies():
    plan,sections=fixture();original=copy.deepcopy(sections)
    tex=render_lecture('答案定位',sections,plan)
    labels=re.findall(r'\\label\{(mathagent:exercise:[0-9a-f]+)\}',tex)
    assert len(labels)==2 and len(set(labels))==2
    assert labels==['mathagent:exercise:'+digest([s['id'],'E1']) for s,_ in sections]
    boundary=tex.index(r'\section*{练习答案}')
    assert tex.index('例题原解')<boundary<tex.index('第一节答案')<tex.index('第二节答案')
    for label in labels:
        assert r'\hyperref['+label+r']{练习 \ref*{'+label+r'} 的解答：}' in tex[boundary:]
    assert r'\textbf{解：}例题原解' in tex
    for _,generated in sections:
        for unit in generated['units']:assert unit['tex'] in tex
    assert sections==original and render_lecture('答案定位',sections,plan)==tex


def test_section_answers_keep_existing_inline_heading_and_position():
    plan,sections=fixture();plan['lecture']['answers_location']='section'
    tex=render_lecture('答案定位',sections,plan)
    assert r'\section*{练习答案}' not in tex and r'\hyperref[' not in tex
    assert r'\textbf{解：}第一节答案' in tex
    assert tex.index('第一节答案')<tex.index(r'\section{第二节}')


def test_generated_exercise_label_namespace_cannot_be_shadowed_by_body():
    plan,sections=fixture()
    sections[0][1]['units'][0]['tex']+=r'\label{mathagent:exercise:fake}'
    with pytest.raises(AgentError) as error:render_lecture('答案定位',sections,plan)
    assert error.value.code=='RESERVED_LABEL_BLOCKED'


@pytest.mark.windows_compile
def test_actual_aux_numbers_and_pdf_links_target_each_exercise(tmp_path):
    from math_agent.compiler import TexCompiler,resolve_xelatex
    import pdfplumber
    if os.name!='nt' or not resolve_xelatex():pytest.skip('Actual Windows XeLaTeX unavailable')
    plan,sections=fixture();tex=render_lecture('答案定位',sections,plan)
    source=tmp_path/'source';source.mkdir()
    (source/'lecture.tex').write_bytes(tex.encode('utf-8'))
    result=TexCompiler(timeout=120).compile(source,'lecture.tex',tmp_path/'build',trusted=True)
    (tmp_path/'compile.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert result['status']=='PASS',result
    aux=Path(result['pdf_path']).with_suffix('.aux').read_text(encoding='utf-8')
    evidence=[]
    with pdfplumber.open(result['pdf_path']) as pdf:
        text='\n'.join(page.extract_text() or '' for page in pdf.pages)
        # The template intentionally shares the definition counter among all
        # numbered teaching environments; 1.1 is the example, 1.2 its exercise.
        for sid,number,anchor in [('S01','1.2','definition.1.2'),('S02','2.1','definition.2.1')]:
            label='mathagent:exercise:'+digest([sid,'E1'])
            line=next(x for x in aux.splitlines() if x.startswith(r'\newlabel{'+label+'}'))
            assert '{{'+number+'}' in line and '{'+anchor+'}' in line
            assert pdf.doc.get_dest(anchor.encode('ascii'))
            links=[{'page':page.page_number,'rect':a['data']['Rect']} for page in pdf.pages
                for a in page.annots if a['data'].get('A',{}).get('D')==anchor.encode('ascii')]
            assert len(links)==1
            assert '练习'+number+'的解答' in re.sub(r'\s+','',text)
            evidence.append({'section_id':sid,'number':number,'anchor':anchor,'label':label,'links':links})
    (tmp_path/'evidence.json').write_text(json.dumps({'status':'PASS','api':'NOT_RUN','teacher_review':'NOT_RUN',
        'references':evidence,'pdf_path':result['pdf_path']},ensure_ascii=False,indent=2),encoding='utf-8')
