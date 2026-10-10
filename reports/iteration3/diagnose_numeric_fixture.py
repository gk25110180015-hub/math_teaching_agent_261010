"""Offline replay after an unexplained UNKNOWN in the full regression."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
for name in list(os.environ):
    if name.startswith('MATH_AGENT_'):
        os.environ.pop(name, None)
os.environ.update(MATH_AGENT_API_KEY='', MATH_AGENT_DEEPSEEK_API_KEY='',
                  MATH_AGENT_LIVE_API_ENABLED='false', MATH_AGENT_LLM_STREAMING='false', MATH_AGENT_LLM_PROVIDER='mock')
from math_agent.mathcheck import check_math, math_child_environment

section = json.loads((ROOT/'tests/fixtures/numeric_evidence_ch02_s04.json').read_bytes())['section']
report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'real_api': 'NOT_RUN',
          'test_kind': 'ACTUAL_LOCAL_SYMPY_DIAGNOSTIC', 'check_math_runs': [], 'direct_child_runs': []}
output = ROOT/'reports/iteration3'/('numeric-diagnostic-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
for _ in range(10):
    started = time.monotonic()
    result = check_math(section)
    report['check_math_runs'].append({'elapsed_seconds': time.monotonic()-started, 'result': result})
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
for _ in range(3):
    started = time.monotonic()
    process = subprocess.run([sys.executable, '-m', 'math_agent.mathcheck', '--child'],
        input=json.dumps(section['calculations'][0], ensure_ascii=False).encode('utf-8'),
        capture_output=True, env=math_child_environment(), timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    report['direct_child_runs'].append({'elapsed_seconds':time.monotonic()-started,
        'returncode':process.returncode, 'stdout':process.stdout.decode('utf-8','replace'),
        'stderr':process.stderr.decode('utf-8','replace')})
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
report['observed_bad_math_runs'] = [index for index,item in enumerate(report['check_math_runs'])
    if item['result']['evidence'][0]['evidence_type'] != 'numeric_spotcheck_passed']
report['status'] = 'REPRODUCED' if report['observed_bad_math_runs'] else 'NOT_REPRODUCED'
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status':report['status'],'report':str(output),
                  'observed_bad_math_runs':report['observed_bad_math_runs']}, ensure_ascii=False))
