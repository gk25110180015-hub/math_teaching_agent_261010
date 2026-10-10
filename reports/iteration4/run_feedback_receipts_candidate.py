"""Offline receipt API validation in an isolated package, with immutable production."""
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
OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--baseline', action='store_true')
parser.add_argument('--combined', action='store_true', help='Stage the Pipeline/provider/helper/prompt candidate too')
parser.add_argument('tests', nargs='*')
args = parser.parse_args()
stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
evidence = OUT/'feedback-receipts-validation'/stamp
evidence.mkdir(parents=True, exist_ok=False)
package = ROOT/'workspace/t'/('fbr-' + stamp[-6:])
package.mkdir(parents=True, exist_ok=False)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = json.loads((OUT/'feedback-receipts-api-ui-manifest.json').read_text(encoding='utf-8'))
files = list(manifest['files'])
if args.combined:
    manifest['pipeline_manifest'] = json.loads((OUT/'feedback-assessment-manifest.json').read_text(encoding='utf-8'))
    files += manifest['pipeline_manifest']['files']
before = {item['source']: sha(ROOT/item['source']) if (ROOT/item['source']).exists() else None for item in files}
assert all(before[item['source']] == item['baseline_sha256'] for item in files)
shutil.copytree(ROOT/'src/math_agent', package/'src/math_agent', ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for folder in ('configs','schemas','templates'):
    if (ROOT/folder).is_dir(): shutil.copytree(ROOT/folder, package/folder)
if not args.baseline:
    for item in files:
        candidate = ROOT/item['candidate'] if '/' in item['candidate'] else OUT/item['candidate']
        assert sha(candidate) == item['candidate_sha256']
        shutil.copyfile(candidate, package/item['source'])
    if not args.combined:
        helper = OUT/'feedback_review.candidate.py'
        shutil.copyfile(helper, package/'src/math_agent/feedback_review.py')
for name in list(os.environ):
    if name.startswith('MATH_AGENT_') or name == 'OPENAI_API_KEY': os.environ.pop(name)
os.environ.update(MATH_AGENT_API_KEY='',MATH_AGENT_DEEPSEEK_API_KEY='',MATH_AGENT_LIVE_API_ENABLED='false')
os.environ['PYTHONPATH'] = str(package/'src')
sys.path.insert(0, str(package/'src'))
import math_agent.service
import pytest
assert Path(math_agent.service.__file__).resolve().is_relative_to(package)
tests = args.tests or ['tests/test_feedback_receipts_api.py']
context = {'mode':'BASELINE_RED' if args.baseline else 'CANDIDATE','package':str(package),'manifest':manifest,
           'tests':{name:sha(ROOT/name) for name in tests},'production_source_before':before}
if not args.baseline:
    context['feedback_schema_candidate_sha256'] = sha(package/'src/math_agent/feedback_review.py')
(evidence/'context.json').write_text(json.dumps(context,indent=2),encoding='utf-8')
print('EVIDENCE=' + str(evidence),flush=True)
with (evidence/'pytest.log').open('x',encoding='utf-8') as stream:
    with redirect_stdout(stream), redirect_stderr(stream):
        code = pytest.main([*tests,'-q','--basetemp',str(package/'test-runtime'),'--junitxml',str(evidence/'pytest.xml')])
after = {name:sha(ROOT/name) if (ROOT/name).exists() else None for name in before}
result = {'status':'PASS' if code==0 and before==after else 'NOT_PASS','pytest_exit_code':code,
          'mode':context['mode'],'production_unchanged':before==after,'source_after':after,
          'real_api':'NOT_RUN','windows_compile':'NOT_RUN','real_browser':'NOT_RUN','teacher_review':'NOT_RUN'}
(evidence/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print((evidence/'pytest.log').read_text(encoding='utf-8')[-7000:])
print(json.dumps(result))
raise SystemExit(code)
