"""Stage candidate source/tests and run offline checks without production writes."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--baseline',action='store_true')
parser.add_argument('--expanded',action='store_true')
args=parser.parse_args()
stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
evidence=OUT/'global-patch-validation'/stamp;evidence.mkdir(parents=True,exist_ok=False)
package=ROOT/'workspace/t'/('gp'+stamp[-6:]);package.mkdir(parents=True,exist_ok=False)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
manifest=json.loads((OUT/'global-strict-patch-manifest.json').read_text(encoding='utf-8'))
before={item['source']:sha(ROOT/item['source']) if (ROOT/item['source']).exists() else None for item in manifest['files']}
assert all(before[item['source']]==item['baseline_sha256'] for item in manifest['files'])
for folder in ('src/math_agent','tests','configs','schemas','templates'):
    if (ROOT/folder).is_dir():
        shutil.copytree(ROOT/folder,package/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(ROOT/'pyproject.toml',package/'pyproject.toml')
for item in manifest['files']:
    candidate=OUT/item['candidate'];assert sha(candidate)==item['candidate_sha256']
    if args.baseline and item['baseline_sha256'] is not None:continue
    target=package/item['source'];target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(candidate,target)
for key in list(os.environ):
    if key.startswith('MATH_AGENT_') or key=='OPENAI_API_KEY':os.environ.pop(key)
os.environ.update(MATH_AGENT_API_KEY='',MATH_AGENT_DEEPSEEK_API_KEY='',MATH_AGENT_LIVE_API_ENABLED='false',
                  PYTHONPATH=str(package/'src'))
sys.path[:0]=[str(package/'src'),str(package/'tests')]
network=[]
original_connect=socket.socket.connect
def connect(instance,address):
    host=address[0] if isinstance(address,tuple) else None
    if host not in ('127.0.0.1','localhost','::1'):
        network.append(repr(address));raise RuntimeError('Offline candidate prohibits external network')
    return original_connect(instance,address)
socket.socket.connect=connect
import pytest
import math_agent.pipeline
assert Path(math_agent.pipeline.__file__).resolve().is_relative_to(package)
tests=['test_global_strict_patch_migration.py']
if args.expanded:
    tests += ['test_global_repair.py','test_global_budget_resume.py','test_global_contract_guard.py',
              'test_local_patch.py','test_teaching_quality_gate.py','test_recheck_feedback_pipeline.py',
              'test_recheck_feedback_history.py','test_feedback_receipts_integration.py',
              'test_cached_review_refresh.py','test_compile_layout_recovery.py']
tests=[str(package/'tests'/name) for name in tests]
context={'mode':'BASELINE_RED' if args.baseline else 'CANDIDATE','manifest':manifest,
         'package':str(package),'tests':tests,'production_before':before}
(evidence/'context.json').write_text(json.dumps(context,indent=2),encoding='utf-8')
print('EVIDENCE='+str(evidence),flush=True)
with (evidence/'pytest.log').open('x',encoding='utf-8') as log:
    with redirect_stdout(log),redirect_stderr(log):
        code=pytest.main([*tests,'-q','-m','not windows_compile','--basetemp',str(package/'t'),
                          '--junitxml',str(evidence/'pytest.xml')])
after={path:sha(ROOT/path) if (ROOT/path).exists() else None for path in before}
result={'status':'PASS' if code==0 and before==after and not network else 'NOT_PASS',
        'mode':context['mode'],'pytest_exit_code':code,'production_unchanged':before==after,
        'source_after':after,'external_network_attempts':network,'real_api':'NOT_RUN',
        'windows_compile':'NOT_RUN','browser':'NOT_RUN','teacher_review':'NOT_RUN'}
(evidence/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print((evidence/'pytest.log').read_text(encoding='utf-8')[-10500:])
print(json.dumps(result))
raise SystemExit(code)
