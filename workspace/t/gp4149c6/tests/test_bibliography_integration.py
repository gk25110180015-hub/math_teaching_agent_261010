from pathlib import Path
import pytest
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.domain import NewRun,ConfirmRequest
from math_agent.worker import Worker
from math_agent.util import digest

SOURCE=r'\documentclass{ctexart}\begin{document}\section{极限}原定义与引用\cite{ExactBook}。\end{document}'
BOOK=r'\documentclass{ctexart}\begin{document}\begin{thebibliography}{99}\bibitem{ExactBook}原稿作者，真实已有条目，2020。\end{thebibliography}\end{document}'

def test_explicit_bibliography_opt_in_preserves_raw_upload_and_locks_provenance(tmp_path):
    ref=tmp_path/'refs';ref.mkdir();(ref/'大学数学（一）(1).tex').write_text(BOOK,encoding='utf-8')
    settings=Settings(workspace=tmp_path/'work',reference_root=ref)
    service=Service(settings)
    run=service.create(NewRun(workflow_id='beamer.from_tex',trusted_input=True,use_reference_bibliography=True))
    run=service.attachments(run['id'],'main.tex',SOURCE.encode())
    evidence=run['input']['source_enrichment']
    assert evidence['added_keys']==['ExactBook']
    assert evidence['manuscript_text_sha256']==digest(BOOK)
    assert (settings.workspace/run['input']['original_source_key']/'main.tex').read_bytes()==SOURCE.encode()
    assert (settings.workspace/run['input']['original_upload_key']).read_bytes()==SOURCE.encode()
    assert r'\bibitem{ExactBook}' in run['input']['parsed']['expanded_tex']
    assert (ref/'大学数学（一）(1).tex').read_text(encoding='utf-8')==BOOK
    service.propose(run['id']);Worker(settings).tick();run=service.store.get_run(run['id']);plan=run['plan']
    assert plan['source_enrichment']==evidence
    assert '原稿作者' in plan['source_enrichment']['entries'][0]['raw_tex']
    service.confirm(run['id'],ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],action_id='test-real-source-enrichment'))
    assert service.store.get_run(run['id'])['approval']['hash']==plan['hash']

def test_without_opt_in_no_manuscript_content_is_injected(tmp_path):
    ref=tmp_path/'refs';ref.mkdir();(ref/'大学数学（一）(1).tex').write_text(BOOK,encoding='utf-8')
    service=Service(Settings(workspace=tmp_path/'work',reference_root=ref))
    run=service.create(NewRun(workflow_id='beamer.from_tex',trusted_input=True))
    run=service.attachments(run['id'],'main.tex',SOURCE.encode())
    assert run['input']['parsed']['expanded_tex']==SOURCE
    assert not run['input'].get('source_enrichment')
