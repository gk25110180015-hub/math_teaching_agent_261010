"""Three isolated repetitions of the immediate predecessor tests and failed math node."""
from datetime import datetime, timezone
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
for name in list(os.environ):
    if name.startswith('MATH_AGENT_'):
        os.environ.pop(name, None)
os.environ.update(MATH_AGENT_API_KEY='', MATH_AGENT_DEEPSEEK_API_KEY='',
    MATH_AGENT_LIVE_API_ENABLED='false', MATH_AGENT_LLM_STREAMING='false', MATH_AGENT_LLM_PROVIDER='mock',
    PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
FILES = ['tests/test_model_routing.py', 'tests/test_multimodel_configuration.py', 'tests/test_multimodel_workflow.py']
TARGET = 'tests/test_numeric_evidence_classification.py::test_actual_ch02_evidence_remains_numeric_and_review_required_but_not_repair_target'

if len(sys.argv) == 3 and sys.argv[1] == '--child':
    import pytest
    output = Path(sys.argv[2])
    metadata = {'real_api':'NOT_RUN', 'teacher_review':'NOT_RUN', 'node_runtime_states':[], 'failures':[]}
    class Evidence:
        def pytest_runtest_setup(self, item):
            metadata['node_runtime_states'].append({'node':item.nodeid, 'cwd':str(Path.cwd()),
                'python_executable':sys.executable, 'stdin_type':type(sys.stdin).__name__,
                'stdout_type':type(sys.stdout).__name__, 'stderr_type':type(sys.stderr).__name__,
                'thread_names':[thread.name for thread in threading.enumerate()],
                'math_env':{name: bool(value) if name.endswith('API_KEY') else value
                            for name,value in os.environ.items() if name.startswith('MATH_AGENT_')}})
        def pytest_runtest_logreport(self, report):
            if report.failed:
                metadata['failures'].append({'node':report.nodeid, 'when':report.when, 'detail':str(report.longrepr)})
    base = ROOT/'workspace/t'/('nm' + uuid.uuid4().hex[:8])
    with output.with_suffix('.log').open('x', encoding='utf-8') as stream:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            code = pytest.main([*FILES,TARGET,'-q','-m','not real_api','--tb=short','--basetemp',str(base),
                                '--junitxml',str(output.with_suffix('.xml')),'-p','no:cacheprovider'], plugins=[Evidence()])
    metadata.update(exit_code=int(code), basetemp=str(base))
    output.with_suffix('.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    raise SystemExit(int(code))

output_dir = ROOT/'reports/iteration3'/('numeric-order-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
output_dir.mkdir()
summary = {'timestamp':datetime.now(timezone.utc).isoformat(), 'real_api':'NOT_RUN',
    'test_files':FILES, 'target':TARGET, 'repetitions':[],
    'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES+[TARGET.split('::')[0]]}}
for index in range(3):
    prefix = output_dir/('repeat-'+str(index+1))
    result = subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',str(prefix)],
        cwd=ROOT, env=os.environ.copy(), capture_output=True)
    summary['repetitions'].append({'exit_code':result.returncode, 'prefix':str(prefix),
        'stdout':result.stdout.decode('utf-8','replace'), 'stderr':result.stderr.decode('utf-8','replace')})
    (output_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
summary['status'] = 'PASS_NO_REPRODUCTION' if all(row['exit_code']==0 for row in summary['repetitions']) else 'FAIL_REPRODUCED'
(output_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':summary['status'],'directory':str(output_dir),'exit_codes':[row['exit_code'] for row in summary['repetitions']]},ensure_ascii=False))
raise SystemExit(0 if summary['status']=='PASS_NO_REPRODUCTION' else 2)
