"""Isolated staged/offline benchmark-version tests, never live API/TeX."""
import contextlib
from datetime import datetime
import importlib.util
import ipaddress
import os
from pathlib import Path
import sys
import uuid

root=Path(__file__).resolve().parents[2]
os.chdir(root)
for key in list(os.environ):
    if key.startswith('MATH_AGENT_') or key in ('PYTEST_ADDOPTS','PYTEST_PLUGINS','PYTEST_CURRENT_TEST'):
        os.environ.pop(key,None)
os.environ.update(MATH_AGENT_API_KEY='',MATH_AGENT_DEEPSEEK_API_KEY='',MATH_AGENT_LIVE_API_ENABLED='false',
    MATH_AGENT_LLM_PROVIDER='mock',MATH_AGENT_LLM_STREAMING='false',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
    PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
sys.dont_write_bytecode=True


def audit(event,args):
    if event=='socket.connect' and isinstance(args[1],tuple):
        host=args[1][0]
        try: allowed=host=='localhost' or ipaddress.ip_address(host).is_loopback
        except ValueError: allowed=False
        if not allowed:raise PermissionError('Offline benchmark regression blocks model network')


sys.addaudithook(audit)
candidate='--candidate' in sys.argv
if candidate:
    path=root/'reports/iteration4/待合并/benchmark-recheck-current.py'
    spec=importlib.util.spec_from_file_location('math_agent.benchmark',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
import pytest
tag=('candidate' if candidate else 'red')+'-'+datetime.now().strftime('%Y%m%d-%H%M%S')
prefix=root/'reports/iteration4'/('benchmark-versions-'+tag)
basetemp=root/'workspace/t'/('bmv'+uuid.uuid4().hex[:8])
os.environ['MATH_AGENT_WORKSPACE']=str(basetemp/'default-workspace')
tests=['tests/test_benchmark_recheck_versions.py']
if candidate:tests+=['tests/test_benchmark_metrics.py','tests/test_benchmark_actor.py','tests/test_benchmark_latency.py']
print(str(prefix),flush=True)
with prefix.with_suffix('.log').open('w',encoding='utf-8') as log:
    with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        result=pytest.main(tests+['-q','--basetemp',str(basetemp),'--junitxml',str(prefix.with_suffix('.xml')),'-p','no:cacheprovider','--tb=short'])
print(prefix.with_suffix('.log').read_text(encoding='utf-8'),flush=True)
raise SystemExit(int(result))
