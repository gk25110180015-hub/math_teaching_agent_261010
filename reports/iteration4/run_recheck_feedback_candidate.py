"""Load proposal modules in this test process only; leave production source intact."""
import hashlib
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
manifest = json.loads((OUT / 'recheck-feedback-api-ui-manifest.json').read_text(encoding='utf-8'))
before = {value['source']: hashlib.sha256((ROOT / value['source']).read_bytes()).hexdigest()
          for value in manifest['files']}
for value in manifest['files']:
    assert before[value['source']] == value['baseline_sha256']
    candidate = OUT / value['candidate']
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == value['candidate_sha256']
    if not value['source'].endswith('.py'):
        continue
    module_name = value['source'].removeprefix('src/').removesuffix('.py').replace('/', '.')
    module = importlib.import_module(module_name)
    exec(compile(candidate.read_text(encoding='utf-8'), str(candidate), 'exec'), module.__dict__)
code = pytest.main(['tests/test_recheck_feedback_api.py', 'tests/test_automatic_recheck_api.py',
                    'tests/test_api.py', 'tests/test_budget_api.py', '-q',
                    '--basetemp', 'workspace/t/fb-candidate',
                    '--junitxml', 'reports/iteration4/recheck-feedback-api-candidate.xml'])
after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in before}
assert before == after
print('PRODUCTION_SOURCE_UNCHANGED=' + json.dumps(after))
raise SystemExit(code)
