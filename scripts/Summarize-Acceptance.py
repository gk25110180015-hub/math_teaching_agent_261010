"""Summarize existing evidence only; never runs tests or upgrades their status."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
reports=root/'reports'
def suite(filename):
    path=reports/filename
    node=ET.parse(path).getroot().find('testsuite')
    counters={k:int(node.attrib[k]) for k in ('tests','errors','failures','skipped')}
    return {**counters,'passed':counters['tests']-sum(counters[k] for k in ('errors','failures','skipped')),
            'seconds':float(node.attrib['time']),'junit':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

matrix=json.loads((reports/'reference_matrix.json').read_text(encoding='utf-8'))
cases=[]
for case in matrix['cases']:
    a=case['attempts'][-1]
    cases.append({k:case[k] for k in ('dataset_id','theme','status','original_unchanged')} |
        {k:a.get(k) for k in ('compile_status','fidelity_status','page_count','rendered_page_count','render_status','draft_pdf_path','pdf_sha256','exact_blocking_issues')} |
        {'teacher_visual_review':'NOT_RUN','real_api':'NOT_RUN'})
result={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),
    'overall':'PARTIALLY_ACCEPTED_EXTERNAL_INPUT_AND_HUMAN_REVIEW_REQUIRED',
    'local_suite':suite('final-local-tests-v3.xml'),
    'browser_suite':suite('test-runs/20260920-003846-307-browser.xml'),
    'real_api_condition':suite('real-api-final.xml'),
    'real_api_status':'NOT_RUN','human_visual_review':'NOT_RUN','model_visual_review':'NOT_RUN',
    'live_lecture_cases':[{'topic':topic,'status':'BLOCKED','reason':'No fresh environment API key or live enablement; no provider request sent.'}
        for topic in ('数列极限','函数极限','导数与微分')],
    'source_beamer_cases':cases,'total_rendered_source_beamer_pages':sum(x['rendered_page_count'] or 0 for x in cases),
    'runtime':json.loads((reports/'runtime_verification.json').read_text(encoding='utf-8-sig')),
    'limitations':['Mock fixtures do not establish provider or mathematical correctness.',
        'Original chapter citations lack bibliography entries; source was not silently modified.',
        'Native trusted-local execution is not filesystem/network isolation.']}
(reports/'acceptance_matrix.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'local':result['local_suite']['passed'],'browser':result['browser_suite']['passed'],
                  'real_api_skipped':result['real_api_condition']['skipped'],
                  'reference_pages':result['total_rendered_source_beamer_pages']},ensure_ascii=False))
