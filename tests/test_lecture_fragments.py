import copy
import json
import os
from pathlib import Path

import pytest

from math_agent.lecture_fragments import normalize_written_section


@pytest.mark.unit
def test_preserve_optional_title_math_and_explanations_around_real_definition_shape():
    raw=r'''前置说明。
\begin{definition}[数列极限]
任取 $\varepsilon>0$，存在正整数 $N$，对所有 $n>N$ 有 $|a_n-A|<\varepsilon$。
\label{def:sequence-limit}
\end{definition}
这里的量词顺序是先任取误差，再选阈值；阈值不能随待验证的 $n$ 改变。'''
    data={'section_id':'S01','units':[{'id':'S01-U01','kind':'definition','tex':raw,'relates_to':None}], 'calculations':[], 'uncertainties':[]}
    original=copy.deepcopy(data)
    normalized,evidence=normalize_written_section(data)
    assert data==original and evidence['status']=='PASS'
    actual=normalized['units'][0]['tex']
    assert '前置说明。' in actual and actual.endswith('这里的量词顺序是先任取误差，再选阈值；阈值不能随待验证的 $n$ 改变。')
    assert r'\textbf{数列极限}' in actual and r'\label{def:sequence-limit}' in actual
    assert r'\begin{definition}' not in actual and r'\end{definition}' not in actual
    assert evidence['units'][0]['raw_hash']!=evidence['units'][0]['normalized_hash']
    assert normalized['units'][0]['id']=='S01-U01'


@pytest.mark.unit
@pytest.mark.parametrize('kind',['theorem','proof','example','exercise','solution'])
def test_one_matching_shell_removed_with_relations_untouched(kind):
    body=r'若 $n>N$，则 $3/n<3/N<\varepsilon$。'
    data={'section_id':'S01','units':[{'id':'U','kind':kind,'tex':'\\begin{'+kind+'}'+body+'\\end{'+kind+'}','relates_to':'T'}],'calculations':[{'id':'calc'}]}
    result,evidence=normalize_written_section(data)
    assert result['units'][0]['tex']==body and result['units'][0]['relates_to']=='T'
    assert result['calculations']==data['calculations'] and evidence['status']=='PASS'


@pytest.mark.unit
def test_math_environments_and_verbatim_like_comments_are_not_stripped():
    body=r'''% \begin{definition} is only a comment.
\begin{proof}
\begin{align}a&=b\\b&=c\end{align}
因此 $a=c$。
\end{proof}'''
    normalized,evidence=normalize_written_section({'units':[{'id':'P','kind':'proof','tex':body}]})
    assert evidence['status']=='PASS'
    assert r'\begin{align}a&=b\\b&=c\end{align}' in normalized['units'][0]['tex']
    assert normalized['units'][0]['tex'].startswith('% \\begin{definition}')


@pytest.mark.unit
@pytest.mark.parametrize('raw',[
    r'\begin{theorem}wrong kind\end{theorem}',
    r'\begin{definition}missing end',
    r'\begin{definition}bad\end{theorem}',
    r'\begin{definition}outer\begin{definition}inner\end{definition}\end{definition}',
    r'\begin{definition}outer\begin{theorem}inner\end{theorem}\end{definition}',
    r'{\begin{definition}inside a group\end{definition}}',
    r'\begin{definition}one\end{definition}\begin{definition}two\end{definition}',
    r'\begin{definition}[unclosed title text',
])
def test_ambiguous_malformed_or_mismatched_shells_are_preserved_and_blocked(raw):
    data={'units':[{'id':'U','kind':'definition','tex':raw}]}
    result,evidence=normalize_written_section(data)
    assert evidence['status']=='BLOCKED'
    assert result==data and evidence['issues'][0]['unit_id']=='U'


@pytest.mark.unit
def test_already_fragment_and_idempotence_preserve_exact_bytes():
    data={'units':[{'id':'U','kind':'solution','tex':'正文 $1/n$。\n','relates_to':'E'}]}
    normalized,evidence=normalize_written_section(data)
    assert normalized==data and evidence['status']=='PASS'
    wrapped={'units':[{'id':'U','kind':'definition','tex':r'\begin{definition}[标题]正文\end{definition}'}]}
    first,_=normalize_written_section(wrapped)
    second,_=normalize_written_section(first)
    assert first==second


@pytest.mark.windows_compile
def test_actual_live_first_section_under_controlled_template_compiles_without_duplicate_shells(tmp_path):
    from math_agent.compiler import TexCompiler,resolve_xelatex
    from math_agent.pipeline import render_lecture
    if os.name!='nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    root=Path(__file__).resolve().parents[1]
    candidates=sorted((root/'workspace/iteration2-live/b/426866cf71d2437b').glob('sS01*/candidate.json'))
    raw_path=next((p for p in candidates if r'\begin{solution}' in p.read_text(encoding='utf-8')),None)
    if raw_path is None:
        pytest.skip('Captured actual live first-section fixture is unavailable')
    raw=json.loads(raw_path.read_text(encoding='utf-8'))
    normalized,evidence=normalize_written_section(raw)
    assert evidence['status']=='PASS'
    snapshot=json.loads((root/'reports/iteration2/live-lectures/smoke/run_snapshot.json').read_text(encoding='utf-8'))
    plan=snapshot['plan']
    spec=next(s for s in plan['sections'] if s['id']=='S01')
    tex=render_lecture(plan['title'],[(spec,normalized)],plan)
    for kind in ('definition','theorem','proof','example','exercise'):
        assert tex.count('\\begin{'+kind+'}')==sum(u['kind']==kind for u in normalized['units'])
    assert r'\begin{solution}' not in tex
    assert '这里的量词顺序' in tex
    answer_start=tex.index(r'\section*{练习答案}')
    assert tex.index('% UNIT S01-U07')>answer_start and tex.index('% UNIT S01-U05')<answer_start
    source=tmp_path/'source';source.mkdir()
    (source/'lecture.tex').write_text(tex,encoding='utf-8')
    (tmp_path/'normalization_evidence.json').write_text(json.dumps({'captured_candidate':str(raw_path),'evidence':evidence},ensure_ascii=False,indent=2),encoding='utf-8')
    result=TexCompiler(timeout=120).compile(source,'lecture.tex',tmp_path/'build',trusted=True)
    (tmp_path/'compile_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert result['status']=='PASS',result
    assert result['passes']>=2 and Path(result['pdf_path']).is_file()
