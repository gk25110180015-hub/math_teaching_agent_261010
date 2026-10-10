"""Generated lecture theorem environments and section references survive conversion."""
import copy
import json
import os
from pathlib import Path
import re

import pytest

from math_agent.beamer import render_beamer, unit_body
from math_agent.beamer_compat import leading_section_label_unit
from math_agent.parsing import parse_tex


SOURCE = r'''\documentclass{ctexart}
\newtheorem{definition}{定义}[section]
\newtheorem{theorem}[definition]{定理}
\newtheorem{exercise}[definition]{练习}
\begin{document}
\maketitle
\section{第一节}
\label{sec:first}
第一节内容；第二节见第\ref{sec:second}节。
\begin{exercise}[求和]\label{ex:first}计算 $1+1$。\end{exercise}
\section{第二节}
\label{sec:second}
第二节内容；第一节见第\ref{sec:first}节。
\begin{exercise}\label{ex:second}计算 $2+2$。\end{exercise}
\section*{练习答案}
\hyperref[ex:first]{练习\ref*{ex:first}的解答：}$2$。
\hyperref[ex:second]{练习\ref*{ex:second}的解答：}$4$。
\end{document}'''


def case(legacy=False):
    parsed = parse_tex(SOURCE)
    if legacy:
        for unit in parsed['units']:
            if unit.get('environment') == 'exercise':
                unit['kind'] = 'opaque_tex'
    plan = {'theme': 'default', 'title': '讲义兼容', 'sections': parsed['sections'],
            'omissions': [], 'additions': []}
    return parsed, plan


@pytest.mark.parametrize('legacy', [False, True])
def test_original_exercise_environment_and_labels_are_lossless(tmp_path, legacy):
    parsed, plan = case(legacy)
    original = copy.deepcopy(parsed)
    exercises = [u for u in parsed['units'] if u.get('environment') == 'exercise']
    assert all(unit_body(u) == u['raw_tex'] for u in exercises)
    result = render_beamer(parsed, plan, tmp_path)
    text = (tmp_path / 'slides.tex').read_text(encoding='utf-8')
    assert result['fidelity']['status'] == 'PASS'
    assert all(u['raw_tex'] in text for u in exercises)
    assert text.count(r'\mathagentsectionlabelcontext' + '\n') == 2
    assert parsed == original


def test_section_binding_only_applies_to_original_heading_labels():
    parsed, _ = case()
    units = {u['id']: u for u in parsed['units']}
    section = next(s for s in parsed['sections'] if s['title'] == '第一节')
    assert leading_section_label_unit(section, units) == section['source_unit_ids'][0]
    exercise = next(u for u in parsed['units'] if u.get('environment') == 'exercise')
    assert leading_section_label_unit({'source_unit_ids': [exercise['id']]}, units) is None
    changed = copy.deepcopy(units)
    changed[section['source_unit_ids'][0]]['raw_tex'] = r'正文之后的\label{not:heading}'
    assert leading_section_label_unit(section, changed) is None


def test_custom_exercise_environment_is_preserved_without_double_definition(tmp_path):
    parsed = parse_tex(r'''\newenvironment{exercise}[1]{\par\textbf{题目：#1}}{\par}
\begin{document}\section{题目}\begin{exercise}{计算}求和。\end{exercise}\end{document}''')
    plan = {'theme': 'default', 'sections': parsed['sections']}
    render_beamer(parsed, plan, tmp_path)
    text = (tmp_path / 'slides.tex').read_text(encoding='utf-8')
    assert r'\@ifundefined{exercise}{\newenvironment{exercise}[1]' in text
    assert r'\begin{exercise}{计算}求和。\end{exercise}' in text


@pytest.mark.windows_compile
@pytest.mark.parametrize('legacy', [False, True])
def test_actual_section_and_exercise_reference_numbers_and_pdf_destinations(tmp_path, legacy):
    from math_agent.compiler import TexCompiler, resolve_xelatex
    import pdfplumber
    if os.name != 'nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    parsed, plan = case(legacy)
    source = tmp_path / 'source'
    rendered = render_beamer(parsed, plan, source)
    assert rendered['fidelity']['status'] == 'PASS'
    result = TexCompiler(timeout=120).compile(source, 'slides.tex', tmp_path / 'build', trusted=True)
    (tmp_path / 'compile.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    assert result['status'] == 'PASS', result
    aux = Path(result['pdf_path']).with_suffix('.aux').read_text(encoding='utf-8')
    exercise_ids = [u['id'] for u in parsed['units'] if u.get('environment') == 'exercise']
    expected = [('sec:first', '1', 'Outline0.1'), ('sec:second', '2', 'Outline0.2'),
                ('ex:first', '1', 'mathagent.exercise.' + exercise_ids[0] + '.0'),
                ('ex:second', '2', 'mathagent.exercise.' + exercise_ids[1] + '.0')]
    with pdfplumber.open(result['pdf_path']) as pdf:
        text = re.sub(r'\s+', '', '\n'.join(p.extract_text() or '' for p in pdf.pages))
        for label, number, anchor in expected:
            line = next(x for x in aux.splitlines() if x.startswith(r'\newlabel{' + label + '}'))
            assert '{{' + number + '}' in line, line
            assert '{' + anchor + '}' in line, line
            assert pdf.doc.get_dest(anchor.encode('ascii'))
            # Beamer \ref uses its same-name slide destination; \hyperref
            # uses the current hyperlink anchor saved in the aux entry.
            link_target = label if label.startswith('sec:') else anchor
            assert pdf.doc.get_dest(link_target.encode('ascii'))
            assert any(a['data'].get('A', {}).get('D') == link_target.encode('ascii')
                       for page in pdf.pages for a in page.annots)
        assert '第二节见第2节' in text and '第一节见第1节' in text
        assert '练习1的解答' in text and '练习2的解答' in text


def test_greek_heading_escape_keeps_variants_and_literal_tex_safe():
    from math_agent.beamer import escape_text
    assert escape_text('εϵφϕ') == ''.join(
        r'\texorpdfstring{\ensuremath{' + command + '}}{' + symbol + '}'
        for symbol, command in [('ε', r'\varepsilon'), ('ϵ', r'\epsilon'),
                                ('φ', r'\varphi'), ('ϕ', r'\phi')])
    assert escape_text('10% {x}_$\\') == r'10\% \{x\}\_\$\textbackslash{}'


@pytest.mark.windows_compile
def test_actual_greek_plain_titles_compile_without_missing_glyphs(tmp_path):
    from math_agent.compiler import TexCompiler, resolve_xelatex
    if os.name != 'nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    parsed = parse_tex(r'''\begin{document}\section{ε 与 α 的估计}
保持正文 $\varepsilon>0$ 与 $\alpha=1$ 原样。
\end{document}''')
    original = copy.deepcopy(parsed)
    plan = {'title': 'ε 与 α', 'sections': parsed['sections'], 'theme': 'default'}
    source = tmp_path / 'source'
    rendered = render_beamer(parsed, plan, source,
        title_generator=lambda frames: {f['frame_id']: 'εϵφϕθϑρϱσςαβγΓΔΩ' for f in frames})
    assert rendered['fidelity']['status'] == 'PASS' and parsed == original
    assert parsed['units'][0]['raw_tex'] in (source / 'slides.tex').read_text(encoding='utf-8')
    result = TexCompiler(timeout=120).compile(source, 'slides.tex', tmp_path / 'build', trusted=True)
    (tmp_path / 'compile.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    assert result['status'] == 'PASS', result
    assert not any(i.get('rule_id') == 'MISSING_GLYPH' for i in result['issues'])
    bookmarks = Path(result['pdf_path']).with_suffix('.out').read_text(encoding='utf-8')
    assert 'varepsilon' not in bookmarks and 'texorpdfstring' not in bookmarks
