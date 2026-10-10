"""Isolated candidate tests with no writes to production source/tests."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent


def main():
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + str(time.time_ns())[-6:]
    out = REPORTS / 'repair-guidance-validation' / name
    out.mkdir(parents=True)
    src = out / 'src'; tests = out / 'tests'
    shutil.copytree(ROOT / 'src/math_agent', src / 'math_agent', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT / 'tests', tests, ignore=shutil.ignore_patterns('__pycache__'))
    files = [('repair_guidance.candidate.py', src / 'math_agent/repair_guidance.py'),
             ('repair-guidance-pipeline.candidate.py', src / 'math_agent/pipeline.py'),
             ('test_repair_guidance.candidate.py', tests / 'test_repair_guidance.py')]
    for source, target in files: shutil.copyfile(REPORTS / source, target)
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('MATH_AGENT_'): env.pop(key)
    env['PYTHONPATH'] = str(src) + os.pathsep + str(tests)
    env['PYTHONIOENCODING'] = 'utf-8'
    names = ['test_repair_guidance.py']
    if '--regressions' in sys.argv:
        names += ['test_local_recovery.py', 'test_global_strict_patch_migration.py', 'test_uncertainty_review.py',
                  'test_global_repair.py', 'test_global_budget_resume.py']
    test_workspace = ROOT / 'workspace' / ('gt' + str(time.time_ns())[-10:])
    assert not test_workspace.exists()
    command = [sys.executable, '-m', 'pytest', *[str(tests / name) for name in names], '-q',
               '--basetemp', str(test_workspace), '--junitxml', str(out / 'junit.xml')]
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True)
    (out / 'stdout.log').write_bytes(result.stdout); (out / 'stderr.log').write_bytes(result.stderr)
    xml = ET.parse(out / 'junit.xml')
    compile_node = next((node for node in xml.iter('testcase') if node.get('name') == 'test_strict_local_patch_is_rechecked_then_actually_compiled_on_windows'), None)
    compilation = 'NOT_RUN' if compile_node is None else ('FAIL' if list(compile_node) else 'PASS')
    data = {'model_calls': 'MOCK_ONLY', 'new_live_api_calls': 0, 'new_windows_compile': compilation,
        'test_workspace': str(test_workspace),
        'teacher_review': 'NOT_RUN', 'returncode': result.returncode, 'elapsed_seconds': time.monotonic() - started,
        'command': command, 'candidates': {source: hashlib.sha256((REPORTS / source).read_bytes()).hexdigest() for source, _ in files}}
    (out / 'result.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(out)); print(result.stdout.decode('utf-8', errors='replace')[-14000:]); print(result.stderr.decode('utf-8', errors='replace')[-3000:])
    return result.returncode


if __name__ == '__main__': raise SystemExit(main())
