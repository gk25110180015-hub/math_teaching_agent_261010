from pathlib import Path
import hashlib

import pytest

from math_agent.manuscript import (audit_manuscript, bibliography_entries,
    chapter_spans, citation_keys, complete_bibliography, extract_chapter, write_prepared_copy)


FULL = r'''\documentclass{article}
\usepackage{hyperref}
\newcommand{\upcite}[1]{\cite{#1}}
\begin{document}
\section*{Introduction}
\section{One}
Original $x<1$.\upcite{A}
\iffalse\section{Hidden}\cite{MissingHidden}\fi
\section{Two}
Other material.\cite{B}
\begin{thebibliography}{99}
\bibitem{A} Author A. Original book. 2017.
\bibitem{B} Author B. \emph{Book B}. \url{https://example.test/book}
\end{thebibliography}
\end{document}
'''
SOURCE = r'\documentclass{article}\begin{document}\section{One}Original $x<1$.\cite{A}\end{document}'


def test_chapter_extraction_retains_exact_math_hidden_answers_and_number():
    spans = chapter_spans(FULL)
    assert [chapter['title'] for chapter in spans] == ['One', 'Two']
    prepared = extract_chapter(FULL, 1)
    assert spans[0]['raw_tex'] in prepared['text']
    assert r'\iffalse\section{Hidden}\cite{MissingHidden}\fi' in prepared['text']
    assert prepared['added_keys'] == ['A'] and prepared['unresolved_keys'] == []
    second = extract_chapter(FULL, 2)
    assert r'\setcounter{section}{1}' in second['text']
    assert second['added_keys'] == ['B']


def test_exact_bibliography_span_and_no_invention():
    entries = bibliography_entries(FULL)
    a = entries['A']
    assert FULL[a['start']:a['end']] == a['raw_tex']
    prepared = complete_bibliography(SOURCE, FULL)
    assert prepared['added_keys'] == ['A']
    assert a['raw_tex'].strip() in prepared['text']
    assert SOURCE.replace(r'\end{document}', '') in prepared['text']
    assert prepared['compile_status'] == 'NOT_RUN'
    unresolved = complete_bibliography(SOURCE.replace('{A}', '{Absent}'), FULL)
    assert unresolved['status'] == 'NEEDS_SOURCE'
    assert unresolved['unresolved_keys'] == ['Absent']
    assert unresolved['text'] == SOURCE.replace('{A}', '{Absent}')


def test_existing_entry_never_replaced_and_conflict_reported():
    original = SOURCE.replace(r'\end{document}', r'\begin{thebibliography}{99}\bibitem{A}Different user record.\end{thebibliography}\end{document}')
    prepared = complete_bibliography(original, FULL)
    assert prepared['text'] == original
    assert prepared['conflicting_keys'] == ['A']
    assert prepared['status'] == 'NEEDS_SOURCE'


def test_empty_existing_bibliography_is_filled_without_duplicate_environment():
    source = SOURCE.replace(r'\end{document}', r'\begin{thebibliography}{99}\end{thebibliography}\end{document}')
    prepared = complete_bibliography(source, FULL)
    assert prepared['text'].count(r'\begin{thebibliography}') == 1
    assert bibliography_entries(FULL)['A']['raw_tex'] in prepared['text']


@pytest.mark.parametrize('payload', [r'\input{../secret}', r'\def\bad{x}', r'\write18{bad}'])
def test_unsafe_bibliography_is_rejected(payload):
    with pytest.raises(ValueError):
        bibliography_entries(FULL.replace('Original book.', payload))


def test_duplicate_key_and_dynamic_citation_rejected():
    with pytest.raises(ValueError):
        bibliography_entries(FULL.replace(r'\bibitem{B}', r'\bibitem{A}'))
    with pytest.raises(ValueError):
        citation_keys(SOURCE.replace('{A}', r'{\Dynamic}'))


def test_write_copy_never_overwrites_source_and_has_provenance(tmp_path):
    original = tmp_path / 'original.tex'
    original.write_text(SOURCE, encoding='utf-8')
    prepared = complete_bibliography(SOURCE, FULL)
    with pytest.raises(ValueError):
        write_prepared_copy(prepared, original, protected_paths=[original])
    output = tmp_path / 'copy.tex'
    write_prepared_copy(prepared, output, protected_paths=[original])
    assert output.with_suffix('.provenance.json').is_file()
    with pytest.raises(FileExistsError):
        write_prepared_copy(prepared, output)
    assert original.read_text(encoding='utf-8') == SOURCE


@pytest.mark.reference
def test_supplied_manuscript_provides_real_missing_three_chapter_entries():
    root = Path(__file__).resolve().parents[2]
    path = root / '大学数学（一）(1).tex'
    if not path.is_file():
        pytest.skip('User manuscript is not available in this installation')
    raw = path.read_bytes()
    report = audit_manuscript(path)
    assert report['sha256'] == hashlib.sha256(raw).hexdigest()
    assert len(report['chapters']) == 8
    assert len(report['bibliography']) == 17
    assert report['unresolved_keys'] == []
    for name, expected in [('第一章', ['BradyWeil']), ('第二章', ['NCBISteadyState']), ('第三章', ['NCBIEnzyme', 'BradyWeil'])]:
        source = (root / name / path.name).read_bytes().decode('utf-8-sig')
        prepared = complete_bibliography(source, raw.decode('utf-8-sig'))
        assert prepared['added_keys'] == expected
        assert not prepared['unresolved_keys']


@pytest.mark.windows_compile
def test_prepared_bibliography_really_resolves_windows_citation(tmp_path):
    from math_agent.compiler import TexCompiler, resolve_xelatex
    engine = resolve_xelatex()
    if engine is None:
        pytest.skip('XeLaTeX unavailable')
    prepared = complete_bibliography(SOURCE, FULL)
    source = tmp_path / 'source'
    write_prepared_copy(prepared, source / 'main.tex')
    result = TexCompiler(str(engine)).compile(source, 'main.tex', tmp_path / 'build', trusted=True)
    assert result['status'] == 'PASS', result
    assert not any(issue['rule_id'] == 'UNRESOLVED_REFERENCE' for issue in result['issues'])
