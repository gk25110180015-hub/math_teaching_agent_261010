"""Run API + Pipeline proposals from one isolated package; preserve production."""
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
api = json.loads((OUT / 'recheck-feedback-api-ui-manifest.json').read_text(encoding='utf-8'))
pipeline = json.loads((OUT / 'recheck-feedback-pipeline-manifest.json').read_text(encoding='utf-8'))
stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
evidence = OUT / 'recheck-feedback-combined' / stamp
evidence.mkdir(parents=True, exist_ok=False)
package = ROOT / 'workspace/t' / ('fbpkg-' + stamp[-6:])
package.mkdir(parents=True, exist_ok=False)
sources = {item['source']: item['baseline_sha256'] for item in api['files']}
sources['src/math_agent/pipeline.py'] = pipeline['base_production_raw_sha256']
for path, expected in sources.items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
shutil.copytree(ROOT / 'src/math_agent', package / 'src/math_agent',
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('configs', 'schemas', 'templates'):
    if (ROOT / name).is_dir():
        shutil.copytree(ROOT / name, package / name)
for item in api['files']:
    candidate = OUT / item['candidate']
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == item['candidate_sha256']
    shutil.copyfile(candidate, package / item['source'])
pipeline_candidate = OUT / 'recheck-feedback-pipeline.candidate.py'
assert hashlib.sha256(pipeline_candidate.read_bytes()).hexdigest() == pipeline['artifacts'][pipeline_candidate.name]['raw_sha256']
shutil.copyfile(pipeline_candidate, package / 'src/math_agent/pipeline.py')
sys.path.insert(0, str(package / 'src'))
for name in list(os.environ):
    if name.startswith('MATH_AGENT_') or name == 'OPENAI_API_KEY':
        os.environ.pop(name)
os.environ.update(MATH_AGENT_LIVE_API_ENABLED='false', MATH_AGENT_API_KEY='',
                  MATH_AGENT_DEEPSEEK_API_KEY='', MATH_AGENT_LLM_STREAMING='false')

import math_agent.pipeline
import math_agent.web.app
import pytest

assert Path(math_agent.pipeline.__file__).resolve().is_relative_to(package)
assert Path(math_agent.web.app.__file__).resolve().is_relative_to(package)
print('ISOLATED_PACKAGE=' + str(package), flush=True)
print('EVIDENCE=' + str(evidence), flush=True)
before = {'source_hashes': sources, 'package': str(package),
          'tests': sys.argv[1:] or ['tests/test_recheck_feedback_api.py', 'tests/test_recheck_feedback_pipeline.py',
                    'tests/test_recheck_feedback_integration.py', 'tests/test_recheck_feedback_workflow.py',
                    'tests/test_automatic_recheck_api.py']}
(evidence / 'context.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
class Capture:
    def __init__(self, original, path):
        self.original, self.file = original, path.open('x', encoding='utf-8')
    def write(self, text):
        self.original.write(text)
        self.file.write(text)
        self.file.flush()
    def flush(self):
        self.original.flush()
        self.file.flush()
    def isatty(self):
        return False
capture = Capture(sys.stdout, evidence / 'pytest.log')
sys.stdout = capture
try:
    code = pytest.main([*before['tests'], '-q', '--basetemp', str(package / 'test-runtime'),
                        '--junitxml', str(evidence / 'pytest.xml')])
finally:
    sys.stdout = capture.original
    capture.file.close()
after = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources}
unchanged = sources == after
result = {'status': 'PASS' if code == 0 and unchanged else 'NOT_PASS', 'pytest_exit_code': code,
          'production_source_unchanged': unchanged, 'source_hashes': after,
          'package': str(package), 'real_api': 'NOT_RUN', 'windows_compile': 'NOT_RUN',
          'real_browser': 'NOT_RUN', 'teacher_review': 'NOT_RUN'}
(evidence / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
assert unchanged
raise SystemExit(code)
