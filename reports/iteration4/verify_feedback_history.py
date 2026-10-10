"""Run only additional history-path tests against the already-frozen joint package."""
from pathlib import Path
import hashlib
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
combined=json.loads((OUT/'recheck-feedback-combined/20260920-155629-04727c/result.json').read_text(encoding='utf-8'))
package=Path(combined['package'])
api=json.loads((OUT/'recheck-feedback-api-ui-manifest.json').read_text(encoding='utf-8'))
pipeline=json.loads((OUT/'recheck-feedback-pipeline-manifest.json').read_text(encoding='utf-8'))
for record in api['files']:
    assert hashlib.sha256((package/record['source']).read_bytes()).hexdigest()==record['candidate_sha256']
assert hashlib.sha256((package/'src/math_agent/pipeline.py').read_bytes()).hexdigest()==pipeline['artifacts']['recheck-feedback-pipeline.candidate.py']['raw_sha256']
files=[ROOT/record['source'] for record in api['files']]+[ROOT/'src/math_agent/pipeline.py']
before={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
for key in list(os.environ):
    if key.startswith('MATH_AGENT_') or key=='OPENAI_API_KEY':os.environ.pop(key)
os.environ.update(MATH_AGENT_API_KEY='',MATH_AGENT_DEEPSEEK_API_KEY='',
                  MATH_AGENT_LIVE_API_ENABLED='false',MATH_AGENT_LLM_STREAMING='false')
sys.path.insert(0,str(package/'src'))
import math_agent.pipeline
import pytest
assert Path(math_agent.pipeline.__file__).is_relative_to(package)
try:
    result=pytest.main(sys.argv[1:])
finally:
    after={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    print('Production source unchanged:',before==after)
    assert before==after
raise SystemExit(result)
