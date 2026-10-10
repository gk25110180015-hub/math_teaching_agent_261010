"""Source typography may be adapted, but mathematical payloads stay exact."""
import copy

import pytest

from math_agent.beamer import check_fidelity, render_beamer, unit_body
from math_agent.parsing import parse_tex


def source(body):
    return parse_tex(r'\begin{document}\section{微分}' + body + r'\end{document}')


def plan(parsed):
    return {'theme': 'default', 'title': '微分', 'sections': parsed['sections'],
            'omissions': [], 'additions': []}


@pytest.mark.parametrize('command,replacement', [
    ('scriptsize', 'footnotesize'), ('tiny', 'footnotesize'),
    ('Large', 'large'), ('LARGE', 'large'), ('huge', 'large'), ('Huge', 'large')])
def test_source_font_adaptation_preserves_math_and_original(tmp_path, command, replacement):
    parsed = source(r'\begin{center}\begin{tikzpicture}\node at (0,0) {'
                    + '\\' + command + r' $\Delta y-\mathrm{d}y$};\end{tikzpicture}\end{center}')
    original = copy.deepcopy(parsed)
    approved = plan(parsed)
    result = render_beamer(parsed, approved, tmp_path)
    tex = (tmp_path / 'slides.tex').read_text(encoding='utf-8')
    assert not any(i['severity'] == 'blocking' for i in result['issues'])
    assert '\\' + command + ' ' not in tex
    assert '\\' + replacement + r' $\Delta y-\mathrm{d}y$' in tex
    assert parsed == original
    assert result['presentation_adaptations'][0]['source_command'] == '\\' + command
    assert result['presentation_adaptations'][0]['replacement'] == '\\' + replacement
    assert check_fidelity(parsed, approved, tex)['status'] == 'PASS'
    assert check_fidelity(parsed, approved, tex.replace(r'\Delta y-\mathrm{d}y',
                                                      r'\Delta y+\mathrm{d}y'))['status'] == 'FAIL'


def test_literal_font_examples_and_comments_are_not_rewritten(tmp_path):
    parsed = source(r'\verb|\scriptsize| % \tiny' + '\n' +
                    r'\begin{verbatim}\scriptsize\end{verbatim}' + '\n' +
                    r'$x^2$ \\scriptsizeName')
    result = render_beamer(parsed, plan(parsed), tmp_path)
    assert not any(i['rule_id'] == 'B-16' for i in result['issues'])
    assert result['presentation_adaptations'] == []
    assert any(r'\verb|\scriptsize|' in unit_body(u) for u in parsed['units'])


@pytest.mark.parametrize('body', [r'\resizebox{1cm}{!}{$a<b$}', r'\scalebox{0.2}{$a<b$}',
                                 r'{\fontsize{4}{5}\selectfont $a<b$}'])
def test_arbitrary_scaling_still_blocks_with_actionable_location(tmp_path, body):
    parsed = source(body)
    result = render_beamer(parsed, plan(parsed), tmp_path)
    issue = next(i for i in result['issues'] if i['rule_id'] == 'B-16')
    assert issue['severity'] == 'blocking'
    assert issue['location']['source_line'] >= 1
    assert issue['suggested_action']


def test_inactive_forbidden_typography_does_not_block(tmp_path):
    parsed = source(r'$x^2$\iffalse\resizebox{1cm}{!}{hidden}\fi')
    result = render_beamer(parsed, plan(parsed), tmp_path)
    assert not any(i['rule_id'] == 'B-16' for i in result['issues'])


def test_article_list_margin_is_not_interpreted_as_overlay(tmp_path):
    parsed = source(r'\begin{itemize}[leftmargin=2em]\item 成本 $C(x)$\item 收入 $R(x)$\end{itemize}')
    result = render_beamer(parsed, plan(parsed), tmp_path)
    tex = (tmp_path/'slides.tex').read_text(encoding='utf-8')
    assert '[leftmargin=2em]' not in tex
    assert r'\item 成本 $C(x)$\item 收入 $R(x)$' in tex
    assert result['presentation_adaptations']
    assert result['fidelity']['status'] == 'PASS'


def test_definition_list_tail_keeps_all_whitespace_and_complete_steps(tmp_path):
    parsed = source(r'\begin{definition}共同前提。\begin{itemize}[leftmargin=2em]'
                    + r'\item $a<b$\item $c<d$\end{itemize}' + '\r\n\r\n'
                    + ('后续完整解释。'+r'\[x+y=z\]'+'\r\n\r\n')*12+r'\end{definition}')
    result = render_beamer(parsed, plan(parsed), tmp_path)
    assert result['fidelity']['status'] == 'PASS'
    assert len(result['frame_plan']) > 2


def test_nested_proof_splits_complete_equations_without_losing_payload(tmp_path):
    step = '这是完整推导。'+r'\[a+b=c\]'+'\r\n\r\n'
    parsed = source(r'\begin{extra}\begin{proofdetail}'+step*15+r'\end{proofdetail}\end{extra}')
    original = copy.deepcopy(parsed)
    result = render_beamer(parsed, plan(parsed), tmp_path)
    tex=(tmp_path/'slides.tex').read_text(encoding='utf-8')
    assert result['fidelity']['status'] == 'PASS'
    assert len(result['frame_plan']) > 3
    assert tex.count(r'\[a+b=c\]') == 15
    assert tex.count(r'\begin{extra}') == tex.count(r'\end{extra}')
    assert tex.count(r'\begin{proofdetail}') == tex.count(r'\end{proofdetail}')
    assert parsed == original
