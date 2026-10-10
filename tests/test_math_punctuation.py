"""Chinese punctuation typography: deterministic tests and real Windows compile evidence."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.lecture_fragments import normalize_written_section


def normalize(tex):
    original={'section_id':'S01','units':[{'id':'U','kind':'explanation','tex':tex,'relates_to':None}],
        'calculations':[{'id':'preserved'}],'calculation_limitations':['unchanged'],'uncertainties':[]}
    result,evidence=normalize_written_section(original)
    assert original['units'][0]['tex']==tex
    assert result['calculations']==original['calculations']
    return result['units'][0]['tex'],evidence


@pytest.mark.parametrize('opening,closing',[(r'\[',r'\]'),(r'\(',r'\)'),('$','$'),('$$','$$'),
    (r'\begin{equation}',r'\end{equation}'),(r'\begin{align*}',r'\end{align*}')])
def test_bare_punctuation_in_explicit_math_gets_text_font_without_losing_character(opening,closing):
    raw='正文。'+opening+r'\frac{1}{n}=0。'+closing+'后文，'
    result,evidence=normalize(raw)
    assert result=='正文。'+opening+r'\frac{1}{n}=0\text{。}'+closing+'后文，'
    assert evidence['status']=='PASS'
    changes=evidence['units'][0]['punctuation_normalizations']
    assert len(changes)==1 and changes[0]['original']=='。' and changes[0]['replacement']==r'\text{。}'
    assert normalize(result)[0]==result


@pytest.mark.parametrize('raw',[
    r'正文，。；：！？、 $a=b$。',
    r'\[a+\text{条件，含{嵌套。}文字！}=b\]',
    r'\[a+\mbox{文字。}=b\]',
    r'\verb|\[x=1。\]|',
    '% \\[x=1。\\]\n正文。',
    r'\[\frac{a，}{b}=1\]',
    r'\[\unknownmacro{汉字。}=1\]',
    r'\[a^。+b_，\]',
    r'\[\left。a\right。\]',
    r'\[{a=b。}\]',
    r'\begin{verbatim}\[x=1。\]\end{verbatim}',
])
def test_text_arguments_comments_verbatim_unknown_groups_and_prose_stay_byte_exact(raw):
    result,evidence=normalize(raw)
    assert result==raw and evidence['status']=='PASS'


def test_cases_and_existing_text_preserved_while_bare_punctuation_is_wrapped():
    raw=r'\[f(x)=\begin{cases}1,&x<0\\2,&x>0\end{cases}，\quad\text{且。}\]'
    result,evidence=normalize(raw)
    assert result==raw.replace('，',r'\text{，}') and evidence['status']=='PASS'


def test_labeled_display_and_punctuation_changes_have_separate_evidence():
    result,evidence=normalize(r'\[a=b。\label{eq:safe}\]')
    assert result==r'\begin{equation}a=b\text{。}\label{eq:safe}\end{equation}'
    record=evidence['units'][0]
    assert record['equation_normalizations'] and record['punctuation_normalizations']


@pytest.mark.parametrize('raw',[r'\[a=b。',r'\[a=b。\)',r'\[a+\text{文字。=b\]'])
def test_ambiguous_math_is_unchanged_and_blocked(raw):
    result,evidence=normalize(raw)
    assert result==raw and evidence['status']=='BLOCKED'


def captured():
    folder=Path(__file__).parent/'fixtures'
    section=json.loads((folder/'live_ch03_math_punctuation.json').read_bytes())
    source=(folder/'live_ch03_math_punctuation.tex').read_text(encoding='utf-8')
    fixed,evidence=normalize_written_section(section)
    after=source
    for before_unit,after_unit in zip(section['units'],fixed['units']):
        if before_unit['tex']!=after_unit['tex']:
            assert source.count(before_unit['tex'])==1
            after=after.replace(before_unit['tex'],after_unit['tex'],1)
    return section,fixed,evidence,source,after


def test_actual_ch03_changes_exactly_seven_punctuation_tokens_and_preserves_other_content():
    section,fixed,evidence,before,after=captured()
    assert evidence['status']=='PASS'
    assert sum(len(u['punctuation_normalizations']) for u in evidence['units'])==7
    assert after.replace(r'\text{。}','。')==before
    assert normalize_written_section(fixed)[0]==fixed
    for key in ('calculations','calculation_limitations','uncertainties'):assert section[key]==fixed[key]


@pytest.mark.windows_compile
def test_actual_ch03_missing_glyph_before_and_full_compile_after(tmp_path):
    from math_agent.compiler import TexCompiler
    from math_agent.util import write_json
    _,_,evidence,before,after=captured()
    results={}
    for name,text in [('before',before),('after',after)]:
        source=tmp_path/(name+'-source');source.mkdir()
        (source/'lecture.tex').write_bytes(text.encode('utf-8'))
        results[name]=TexCompiler().compile(source,'lecture.tex',tmp_path/(name+'-build'),trusted=True)
    write_json(tmp_path/'pre-post-evidence.json',{'normalization':evidence,'compile':results,'teacher_visual_review':'NOT_RUN'})
    assert results['before']['status']=='FAIL'
    assert sum(i['rule_id']=='MISSING_GLYPH' for i in results['before']['issues'])==7
    assert results['after']['status']=='PASS',results['after']
    assert results['before']['page_count']==results['after']['page_count']==3
