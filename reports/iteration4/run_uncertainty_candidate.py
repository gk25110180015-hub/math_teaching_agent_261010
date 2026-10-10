"""Isolated report-only package and tests; no production writes or API credentials."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--delivered-tests', action='store_true')
parser.add_argument('tests', nargs='*')
args = parser.parse_args()
stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
evidence = REPORTS/'uncertainty-validation'/stamp
evidence.mkdir(parents=True, exist_ok=False)
package = ROOT/'workspace/t'/('ud-' + stamp[-6:])
package.mkdir(parents=True, exist_ok=False)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = json.loads((REPORTS/'uncertainty-review-manifest.json').read_text(encoding='utf-8'))
files = manifest['files']
before = {i['source']:sha(ROOT/i['source']) if (ROOT/i['source']).exists() else None for i in files}
assert all(before[i['source']] == i['baseline_sha256'] for i in files)
shutil.copytree(ROOT/'src/math_agent', package/'src/math_agent', ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for folder in ('configs','schemas','templates'):
    if (ROOT/folder).is_dir(): shutil.copytree(ROOT/folder, package/folder)
for item in files:
    candidate = REPORTS/item['candidate']
    assert sha(candidate) == item['candidate_sha256']
    (package/item['source']).parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(candidate, package/item['source'])
for key in list(os.environ):
    if key.startswith('MATH_AGENT_') or key == 'OPENAI_API_KEY': os.environ.pop(key)
os.environ.update(MATH_AGENT_API_KEY='', MATH_AGENT_DEEPSEEK_API_KEY='', MATH_AGENT_LIVE_API_ENABLED='false',
                  PYTHONPATH=str(package/'src'))
sys.path.insert(0, str(ROOT/'tests'))
sys.path.insert(0, str(package/'src'))
import math_agent.uncertainty_review
import pytest
assert Path(math_agent.uncertainty_review.__file__).resolve().is_relative_to(package)
tests = args.tests or ['reports/iteration4/test_uncertainty_review_candidate.py']
if args.delivered_tests:
    tests=[str(package/'tests/test_uncertainty_review.py'),*args.tests]
context = {'manifest':manifest,'tests':{name:sha(ROOT/name) for name in tests},'package':str(package),
           'production_before':before, 'mode':'MOCK_PROVIDER_AND_COMPILER_REAL_SQLITE'}
(evidence/'context.json').write_text(json.dumps(context,ensure_ascii=False,indent=2),encoding='utf-8')
print('EVIDENCE='+str(evidence), flush=True)
with (evidence/'pytest.log').open('x',encoding='utf-8') as stream:
    with redirect_stdout(stream), redirect_stderr(stream):
        code=pytest.main([*tests,'-q','--basetemp',str(package/'test-runtime'),'--junitxml',str(evidence/'pytest.xml')])
after={name:sha(ROOT/name) if (ROOT/name).exists() else None for name in before}
result={'status':'PASS' if code==0 and before==after else 'NOT_PASS','pytest_exit_code':code,
        'production_unchanged':before==after,'api_calls':0,'windows_compile':'NOT_RUN',
        'browser':'NOT_RUN','teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'}
(evidence/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print((evidence/'pytest.log').read_text(encoding='utf-8')[-14000:])
print(json.dumps(result))
raise SystemExit(code)
