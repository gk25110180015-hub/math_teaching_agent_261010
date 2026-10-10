"""Load the frozen candidate into this mock-only test interpreter."""
from pathlib import Path
import hashlib
import json
import os
import sys

for key in list(os.environ):
    if key.startswith('MATH_AGENT_'):
        del os.environ[key]
os.environ.update(MATH_AGENT_API_KEY='', MATH_AGENT_DEEPSEEK_API_KEY='', MATH_AGENT_LIVE_ENABLED='false')

import math_agent.pipeline as pipeline
import pytest

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
paths=[ROOT/'src/math_agent/pipeline.py',ROOT/'src/math_agent/prompts/reviewer_math.md']
before={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
manifest=json.loads((OUT/'recheck-feedback-pipeline-manifest.json').read_text(encoding='utf-8'))
raw=(OUT/'recheck-feedback-pipeline.candidate.py').read_bytes()
assert hashlib.sha256(raw).hexdigest()==manifest['artifacts']['recheck-feedback-pipeline.candidate.py']['raw_sha256']
exec(compile(raw.decode('utf-8'),str(paths[0]),'exec'),pipeline.__dict__)
try:
    result=pytest.main(sys.argv[1:])
finally:
    after={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    print('Production pipeline/reviewer raw SHA unchanged:',before==after,after)
    assert before==after
raise SystemExit(result)
