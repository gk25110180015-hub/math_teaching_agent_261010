"""Run candidate guard + API/feedback regressions in a new isolated src package."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
token = uuid.uuid4().hex[:6]
isolated = ROOT / 'workspace/t' / ('atg-' + token)
isolated.mkdir(parents=True, exist_ok=False)
shutil.copytree(ROOT / 'src', isolated / 'src', ignore=shutil.ignore_patterns('__pycache__'))
entries = json.loads((OUT / 'recheck-feedback-api-ui-manifest.json').read_bytes())['files']
entries += json.loads((OUT / 'review-evidence-attribution-manifest.json').read_bytes())['files']
for entry in entries:
    candidate = OUT / entry['candidate']
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == entry['candidate_sha256']
    target = isolated / entry['source']
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate, target)
evidence = OUT / ('review-evidence-guard-tests-' + token)
evidence.mkdir()
tests = sys.argv[1:] or [
    'tests/test_review_evidence_attribution_candidate.py', 'tests/test_review_evidence_guard.py',
    'tests/test_review_scope.py', 'tests/test_review_rendering_contract.py',
    'tests/test_recheck_feedback_pipeline.py', 'tests/test_recheck_feedback_integration.py',
    'tests/test_recheck_feedback_history.py', 'tests/test_cached_review_refresh.py',
]
env = os.environ.copy()
env['PYTHONPATH'] = str(isolated / 'src')
env['PYTHONIOENCODING'] = 'utf-8'
command = [sys.executable, '-m', 'pytest', '-q', *tests, '--basetemp', str(isolated / 'test-runtime'),
           '--junitxml', str(evidence / 'junit.xml')]
result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
(evidence / 'pytest.log').write_text(result.stdout, encoding='utf-8')
(evidence / 'manifest.json').write_text(json.dumps({'command': command, 'returncode': result.returncode,
    'isolated': str(isolated), 'files': entries, 'api_calls': 0, 'production_changes': 0,
    'classification': 'MOCK_TESTS_NO_REAL_API_OR_WINDOWS_COMPILATION'}, ensure_ascii=False, indent=2), encoding='utf-8')
print(result.stdout)
print(json.dumps({'evidence': str(evidence), 'isolated': str(isolated), 'returncode': result.returncode}, ensure_ascii=False))
raise SystemExit(result.returncode)
