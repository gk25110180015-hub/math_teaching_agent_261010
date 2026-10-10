"""Both workflows preserve actionable compile failures (mock compiler/model)."""
import json

import pytest

from math_agent.domain import NewRun, DecisionsRequest, ConfirmRequest, ExecuteRequest
from math_agent.pipeline import Pipeline
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.worker import Worker


@pytest.mark.parametrize('workflow', ['lecture.generate', 'beamer.from_tex'])
def test_worker_preserves_approval_and_reports_concrete_global_failure(tmp_path, monkeypatch, workflow):
    service = Service(Settings(workspace=tmp_path))
    worker = Worker(service.settings)
    run = service.create(NewRun(workflow_id=workflow, topic='数列极限', trusted_input=True))
    rid = run['id']
    if workflow == 'beamer.from_tex':
        service.attachments(rid, 'source.tex', rb'\begin{document}\section{A}$a<b$\end{document}')
    service.propose(rid)
    worker.tick()
    plan = service.store.get_run(rid)['plan']
    if plan.get('questions'):
        plan = service.decisions(rid, DecisionsRequest(expected_plan_revision=plan['revision'], decisions=[
            {'question_id':q['id'], 'question_revision':q['revision'],
             'selected_option_ids':[q['options'][0]['id']]} for q in plan['questions']]))
    service.confirm(rid, ConfirmRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], action_id='approve'))
    approval = service.store.get_run(rid)['approval']
    sections = [(plan['sections'][0], {'units':[{'id':'A', 'kind':'explanation', 'tex':'$a<b$'}]})]
    monkeypatch.setattr(Pipeline, 'lecture', lambda self, plan: (sections, []))
    issue = {'rule_id':'MISSING_FILE', 'severity':'blocking', 'message':'Missing diagram.pdf',
             'location':{'file':'lecture.tex' if workflow=='lecture.generate' else 'slides.tex', 'source_line':17}}
    monkeypatch.setattr(Pipeline, 'compile', lambda *args: {'status':'FAIL', 'issues':[issue, issue], 'pdf_path':None})
    service.execute(rid, ExecuteRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], idempotency_key='build'))
    worker.tick()
    failed = service.store.get_run(rid)
    assert failed['status'] == 'BLOCKED'
    assert failed['error']['code'] == 'QUALITY_BLOCKED'
    assert 'MISSING_FILE' in failed['error']['message'] and '17' in failed['error']['message']
    assert 'diagram.pdf' in failed['error']['message']
    assert failed['approval'] == approval
    latest = json.loads((tmp_path/'runs'/rid/'latest_build.json').read_text(encoding='utf-8'))
    output = tmp_path/latest['storage_key']
    quality = json.loads((output/'quality_report.json').read_text(encoding='utf-8'))
    assert len(quality['issues']) == 1
    assert 'MISSING_FILE' in (output/'quality_report.md').read_text(encoding='utf-8')
    before = (output/'quality_report.json').read_bytes()
    job = service.retry(rid)
    assert job['attempt'] == 1
    assert service.store.get_run(rid)['approval'] == approval
    assert (output/'quality_report.json').read_bytes() == before
