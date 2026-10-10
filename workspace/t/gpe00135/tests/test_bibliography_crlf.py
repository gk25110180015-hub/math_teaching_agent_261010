"""Windows CRLF input must survive bibliography enrichment as exact UTF-8 bytes."""
import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from math_agent.domain import NewRun
from math_agent.manuscript import complete_bibliography
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import digest


SOURCE='\r\n'.join([
    r'\documentclass[UTF8,fontset=fandol]{ctexart}',
    r'\usepackage{xcolor,mdframed}',
    r'\mdfdefinestyle{sample}{%',
    r'linewidth=0.8pt,',
    r'backgroundcolor=gray!5',
    r'}',
    r'\begin{document}',
    r'\section{极限}',
    r'\begin{mdframed}[style=sample]',
    r'保留原文 $1/n\to0$，引用\cite{ExactBook}。',
    r'\end{mdframed}',
    r'\end{document}',
    '',
])
BOOK='\r\n'.join([
    r'\documentclass{ctexart}',r'\begin{document}',r'\begin{thebibliography}{9}',
    r'\bibitem{ExactBook} 原稿条目，2020。',r'\end{thebibliography}',r'\end{document}','',
])


def prepare(tmp_path):
    refs=tmp_path/'refs';refs.mkdir()
    manuscript=refs/'大学数学（一）(1).tex';manuscript.write_bytes(BOOK.encode('utf-8'))
    settings=Settings(workspace=tmp_path/'work',reference_root=refs,live_api_enabled=False,api_key=SecretStr(''))
    service=Service(settings,actor='benchmark_driver')
    run=service.create(NewRun(workflow_id='beamer.from_tex',trusted_input=True,use_reference_bibliography=True))
    run=service.attachments(run['id'],'main.tex',SOURCE.encode('utf-8'))
    return settings,run,manuscript


def test_enrichment_preserves_exact_output_bytes_and_crlf_macro_arguments(tmp_path):
    settings,run,manuscript=prepare(tmp_path)
    payload=run['input'];prepared=settings.workspace/payload['source_key']/payload['main_file']
    expected=complete_bibliography(SOURCE,BOOK)['text'].encode('utf-8')
    actual=prepared.read_bytes()
    assert actual==expected
    assert b'\r\r\n' not in actual
    assert digest(actual)==payload['source_enrichment']['output_text_sha256']
    assert payload['parsed']['expanded_tex'].encode('utf-8')==expected
    assert (settings.workspace/payload['original_source_key']/payload['main_file']).read_bytes()==SOURCE.encode('utf-8')
    assert (settings.workspace/payload['original_upload_key']).read_bytes()==SOURCE.encode('utf-8')
    assert manuscript.read_bytes()==BOOK.encode('utf-8')
    assert payload['source_key']!=payload['original_source_key']


@pytest.mark.windows_compile
def test_crlf_enriched_source_macro_and_reference_really_compile(tmp_path):
    from math_agent.compiler import TexCompiler,resolve_xelatex
    from math_agent.util import write_json
    if os.name!='nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    settings,run,_=prepare(tmp_path)
    source=settings.workspace/run['input']['source_key']
    result=TexCompiler(timeout=120).compile(source,'main.tex',tmp_path/'build',trusted=True)
    write_json(tmp_path/'compile.json',result)
    assert result['status']=='PASS',result
    assert result['passes']>=2 and Path(result['pdf_path']).is_file()
    assert r'\bibcite{ExactBook}{1}' in Path(result['pdf_path']).with_suffix('.aux').read_text(encoding='utf-8')
