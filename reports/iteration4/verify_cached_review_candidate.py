"""Load proposed pipeline only into this test interpreter; leave src untouched."""
from pathlib import Path
import hashlib
import sys

import math_agent.pipeline as pipeline
import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'src/math_agent/pipeline.py'
before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
candidate = (Path(__file__).parent / 'cached-review-refresh.candidate.py').read_text(encoding='utf-8')
exec(compile(candidate, str(SOURCE), 'exec'), pipeline.__dict__)
result = pytest.main(sys.argv[1:])
after = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
print(f'Production pipeline SHA unchanged: {before == after}; {after}')
assert before == after
raise SystemExit(result)
