"""AMS text arguments form a separate text scope, retaining all body bytes."""
import json
from pathlib import Path

import pytest

from math_agent.lecture_fragments import normalize_written_section


def normalize(tex):
    section={'section_id':'S01','units':[{'id':'U1','kind':'theorem','tex':tex,'relates_to':None}],
        'calculations':[],'uncertainties':[]}
    result,evidence=normalize_written_section(section)
    assert section['units'][0]['tex']==tex
    return result['units'][0]['tex'],evidence


@pytest.mark.parametrize('tex',[
    r'\[\text{$\varepsilon$--$N$ 定义}\]',
    r'\[\begin{array}{c|c}\text{对任意 $\varepsilon>0$}&\text{统一的正整数 $N$}\end{array}\]',
    r'\[\text{含 \(x>0\) 的文字}\]',
    r'\[\text{$a+\text{$b$ 条件}$}\]',
    r'\[\text{保留中文，及 $a$。}\]',
    r'\[\text{\{转义括号\}与 $x$}\]',
])
def test_known_text_argument_has_independent_math_scope_and_is_byte_exact(tex):
    output,evidence=normalize(tex)
    assert evidence['status']=='PASS',evidence
    assert output==tex


@pytest.mark.parametrize('tex',[
    r'\[$a$\]',
    r'\[\text{$a}\]',
    r'\[\text{\(a$}\]',
    r'\[\text{$a$\]',
    r'\[\unknown{$a$}\]',
    r'\[\text{\begin{proof}$a$\end{proof}}\]',
])
def test_actual_mixed_math_unknown_macro_and_unbalanced_text_still_block(tex):
    output,evidence=normalize(tex)
    assert evidence['status']=='BLOCKED' and output==tex


def test_text_argument_does_not_mask_outer_label_or_comment_verbatim():
    raw=r'\[a+\text{$b$ 字面}。\label{eq:one}\]'
    output,evidence=normalize(raw)
    assert evidence['status']=='PASS'
    assert output==r'\begin{equation}a+\text{$b$ 字面}\text{。}\label{eq:one}\end{equation}'
    literal=r'\verb|\text{$notbalanced}| % \text{$bad}'+'\n'+r'\[\text{$a$}\]'
    assert normalize(literal)[0]==literal


def captured_units():
    return json.loads((Path(__file__).parent/'fixtures/live_ch01_s05_text_math.json').read_bytes())


def test_actual_original_and_rejected_patch_u02_are_structurally_valid_without_edits():
    for name,unit in captured_units()['units'].items():
        output,evidence=normalize(unit['tex'])
        assert evidence['status']=='PASS',(name,evidence)
        assert output==unit['tex']


def test_actual_original_section_retains_persisted_recovery_base_hash():
    from math_agent.util import digest
    captured=captured_units()
    normalized,evidence=normalize_written_section(captured['original_section'])
    assert evidence['status']=='PASS'
    assert digest(normalized)==captured['expected_base_hash']


def test_nested_text_parser_has_a_finite_depth_limit():
    raw=r'\['+r'\text{'*26+'x'+'}'*26+r'\]'
    output,evidence=normalize(raw)
    assert evidence['status']=='BLOCKED' and output==raw


@pytest.mark.windows_compile
def test_actual_captured_table_compiles_as_tex_and_keeps_layout_gate(tmp_path):
    from math_agent.compiler import TexCompiler
    from math_agent.pipeline import render_lecture
    from math_agent.util import write_json
    unit=captured_units()['units']['patch']
    plan={'provider':'mock','lecture':{'answers_location':'end'}}
    spec={'id':'S05','title':'方法选择'}
    section={'section_id':'S05','units':[unit],'calculations':[],'uncertainties':[]}
    normalized,evidence=normalize_written_section(section)
    assert normalized==section and evidence['status']=='PASS'
    source=tmp_path/'source';source.mkdir()
    (source/'lecture.tex').write_bytes(render_lecture('实际表格语法探针',[(spec,normalized)],plan).encode('utf-8'))
    result=TexCompiler().compile(source,'lecture.tex',tmp_path/'build',trusted=True)
    write_json(tmp_path/'evidence.json',{'normalization':evidence,'compile':result,'teacher_visual_review':'NOT_RUN'})
    assert Path(result['pdf_path']).is_file()
    assert not any(i['rule_id'] in ('LATEX_ERROR','TEX_FATAL','UNDEFINED_CONTROL_SEQUENCE','MISSING_GLYPH') for i in result['issues'])
    # A valid AMS table may still be too wide: keep the real layout outcome.
    assert all(i['rule_id']=='OVERFULL_BOX' for i in result['issues'] if i['severity']=='blocking'),result
