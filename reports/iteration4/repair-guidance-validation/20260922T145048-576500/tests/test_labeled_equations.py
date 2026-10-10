"""Only display delimiters change; actual Windows aux/PDF links prove the target."""
import copy
import json
import os
from pathlib import Path
import re

import pytest

from math_agent.lecture_fragments import normalize_written_section
from math_agent.util import digest


def section(tex, kind='solution'):
    return {'section_id':'S01','units':[{'id':'S01.U05','kind':kind,'tex':tex,'relates_to':'S01.U04'}],
            'calculations':[], 'uncertainties':[]}


def test_unique_labeled_display_gets_number_without_any_math_body_change():
    body='\n'+r'\lim_{n\to\infty}\frac{1}{n}=0.'+'\n'+r'\label{eq:reciprocal-limit}'+'\n'
    raw='前文。\\['+body+'\\]后文。'
    data=section(raw);original=copy.deepcopy(data)
    result,evidence=normalize_written_section(data)
    assert data==original and evidence['status']=='PASS'
    assert result['units'][0]['tex']=='前文。\\begin{equation}'+body+'\\end{equation}后文。'
    change=evidence['units'][0]['equation_normalizations'][0]
    assert change['label']=='eq:reciprocal-limit' and change['preserved_body_hash']==digest(body)
    assert change['mathematical_body_preserved'] is True
    assert evidence['unit_ids_preserved'] and evidence['relations_preserved']
    assert not evidence['mathematical_content_rewritten']
    assert result['calculations']==original['calculations']
    second,second_evidence=normalize_written_section(result)
    assert second==result and second_evidence['status']=='PASS'


def test_shell_removal_and_labeled_equation_normalization_compose():
    data=section(r'\begin{solution}\[a=b\label{eq:one}\]\end{solution}')
    normalized,evidence=normalize_written_section(data)
    assert normalized['units'][0]['tex']==r'\begin{equation}a=b\label{eq:one}\end{equation}'
    assert evidence['status']=='PASS' and evidence['units'][0]['removed_spans']


@pytest.mark.parametrize('raw',[
    r'\[a=b\]',
    r'\[a=b\tag{A}\label{eq:one}\]',
    r'\[a=b\tag*{A}\label{eq:one}\]',
    r'\begin{equation}a=b\label{eq:one}\end{equation}',
    '% \\[a=b\\label{eq:comment}\\]\n普通正文。',
    r'\verb|\[a=b\label{eq:verbatim}\]|',
])
def test_unlabeled_tagged_numbered_and_non_executing_displays_are_unchanged(raw):
    data=section(raw)
    result,evidence=normalize_written_section(data)
    assert result==data and evidence['status']=='PASS'


@pytest.mark.parametrize('raw',[
    r'\[a=b\label{eq:one}\label{eq:two}\]',
    r'\[a=b\label{bad label}\]',
    r'\[a=b\label{eq:{dynamic}}\]',
    r'\[a=b\label{eq:one}\]\label{eq:one}',
    r'\[\begin{equation}a=b\label{eq:one}\end{equation}\]',
    r'\[\begin{align}a&=b\label{eq:one}\end{align}\]',
    r'\[\[a=b\label{eq:one}\]\]',
    r'\[a=b\notag\label{eq:one}\]',
    r'\[{a=b\label{eq:one}}\]',
    r'\begin{equation}\[a=b\label{eq:one}\]\end{equation}',
])
def test_ambiguous_labeled_display_preserves_entire_original_and_blocks(raw):
    data=section(raw)
    result,evidence=normalize_written_section(data)
    assert result==data and evidence['status']=='BLOCKED'
    assert evidence['issues'][0]['unit_id']=='S01.U05'


def test_duplicate_label_in_another_unit_blocks_conversion():
    data=section(r'\[a=b\label{eq:one}\]')
    data['units'].append({'id':'S01.U06','kind':'explanation','tex':r'\label{eq:one}第二处。'})
    result,evidence=normalize_written_section(data)
    assert result==data and evidence['status']=='BLOCKED'


def test_aligned_body_is_preserved_under_one_equation_number():
    body=r'\begin{aligned}a&=b\\c&=d\end{aligned}\label{eq:one}'
    result,evidence=normalize_written_section(section(r'\['+body+r'\]'))
    assert evidence['status']=='PASS'
    assert result['units'][0]['tex']==r'\begin{equation}'+body+r'\end{equation}'


@pytest.mark.windows_compile
def test_captured_two_live_sections_resolve_to_equation_anchor_and_pdf_links(tmp_path):
    from math_agent.compiler import TexCompiler,resolve_xelatex
    from math_agent.pipeline import render_lecture
    import pdfplumber
    if os.name!='nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    root=Path(__file__).resolve().parents[1]
    captured=root/'reports/iteration2/labeled_equations/before'
    paths=[captured/'0-candidate.json',captured/'1-candidate.json',captured/'5-run_snapshot.json']
    if not all(p.is_file() for p in paths):
        pytest.skip('Captured two-section live fixture is unavailable')
    raw=[json.loads(p.read_text(encoding='utf-8')) for p in paths[:2]]
    plan=json.loads(paths[2].read_text(encoding='utf-8'))['plan']
    normalized=[];normalizations=[]
    for generated in raw:
        value,evidence=normalize_written_section(generated)
        assert evidence['status']=='PASS',evidence
        normalized.append(value);normalizations.append(evidence)
    assert sum(len(u['equation_normalizations']) for e in normalizations for u in e['units'])==1
    rows={}
    for label,values in [('before',raw),('after',normalized)]:
        source=tmp_path/label/'source';source.mkdir(parents=True)
        sections=[(next(s for s in plan['sections'] if s['id']==v['section_id']),v) for v in values]
        tex=render_lecture(plan['title'],sections,plan)
        (source/'lecture.tex').write_text(tex,encoding='utf-8')
        compiled=TexCompiler(timeout=120).compile(source,'lecture.tex',tmp_path/label/'build',trusted=True)
        (tmp_path/label/'compile.json').write_text(json.dumps(compiled,ensure_ascii=False,indent=2),encoding='utf-8')
        assert compiled['status']=='PASS',compiled
        aux=(tmp_path/label/'build/lecture.aux').read_text(encoding='utf-8')
        aux_line=next(x for x in aux.splitlines() if x.startswith(r'\newlabel{eq:reciprocal-limit}'))
        anchor=re.search(r'\}\{([^{}]+)\}\{\}\}$',aux_line).group(1)
        links=[]
        with pdfplumber.open(compiled['pdf_path']) as reader:
            assert reader.doc.get_dest(anchor.encode('ascii'))
            for index,page in enumerate(reader.pages,1):
                for annot in page.annots:
                    item=annot['data'];destination=item.get('A',{}).get('D',item.get('Dest'))
                    if isinstance(destination,bytes):destination=destination.decode('ascii')
                    if destination==anchor:
                        links.append({'page':index,'destination':destination,'rect':[float(x) for x in item['Rect']]})
            assert len(links)>=2
            rows[label]={'compile':compiled,'aux_line':aux_line,'anchor':anchor,'links':links,'page_count':len(reader.pages)}
    assert rows['before']['anchor'].startswith('definition.')
    assert rows['after']['anchor'].startswith('equation.')
    (tmp_path/'evidence.json').write_text(json.dumps({'normalizations':normalizations,'results':rows,
        'api_calls':0,'teacher_review':'NOT_RUN'},ensure_ascii=False,indent=2),encoding='utf-8')
