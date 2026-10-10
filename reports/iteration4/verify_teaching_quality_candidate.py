"""Run combined candidate in an isolated interpreter, with candidate prompt copies."""
from pathlib import Path
import hashlib
import shutil
import sys

import math_agent.pipeline as pipeline
import math_agent.provider as provider
import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
paths = [ROOT/'src/math_agent/pipeline.py', ROOT/'src/math_agent/prompts/reviewer_math.md']
before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
prompts = OUT/'teaching-quality-candidate-prompts'
prompts.mkdir(exist_ok=True)
for path in provider.PROMPTS.glob('*.md'):
    shutil.copyfile(path, prompts/path.name)
shutil.copyfile(OUT/'reviewer_math_v5.candidate.md', prompts/'reviewer_math.md')
provider.PROMPTS = prompts
candidate = (OUT/'cached-teaching-quality-combined.candidate.py').read_text(encoding='utf-8')
exec(compile(candidate, str(paths[0]), 'exec'), pipeline.__dict__)
result = pytest.main(sys.argv[1:])
after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
print('Production source and reviewer prompt hashes unchanged:', before == after)
assert before == after
raise SystemExit(result)
