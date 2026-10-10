"""One explicit offline regression invocation; writes reports and isolated basetemp only."""
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.dont_write_bytecode = True
for key in list(os.environ):
    if key.startswith('MATH_AGENT_'):
        os.environ.pop(key, None)
tag = datetime.datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
base = ROOT / 'workspace' / 't' / uuid.uuid4().hex[:8]
assert base.is_relative_to(ROOT / 'workspace' / 't') and not base.exists()
prefix = ROOT / 'reports' / 'iteration2' / ('local-final-' + tag)
os.environ.update(MATH_AGENT_API_KEY='', MATH_AGENT_LIVE_API_ENABLED='false',
                  MATH_AGENT_LLM_STREAMING='false', MATH_AGENT_LLM_PROVIDER='mock',
                  MATH_AGENT_WORKSPACE=str(base / 'default-workspace'),
                  PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
test_files = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'tests').glob('test_*.py'))

def snapshot():
    paths = {ROOT / 'pyproject.toml', ROOT / 'uv.lock'}
    paths.update((ROOT / 'tests').glob('test_*.py'))
    for directory in ('src', 'tests/fixtures', 'configs', 'templates'):
        root = ROOT / directory
        if root.exists():
            paths.update(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

metadata = {
    'started_at': datetime.datetime.now().astimezone().isoformat(),
    'suite': 'All top-level tests/test_*.py after frozen numeric-evidence classification, provider JSON feedback and reviewer prompt v4 deployment',
    'python': platform.python_version(), 'platform': platform.platform(),
    'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'freeze_basis': 'Root FREEZE confirmation; environment numeric-classification 55 PASS; source/tests frozen before invocation',
    'basetemp': base.relative_to(ROOT).as_posix(),
    'real_api': 'DISABLED_NOT_RUN', 'provider': 'MOCK_OR_FAKE_TRANSPORT',
    'teacher_visual_review': 'NOT_RUN', 'e2e_directory': 'NOT_COLLECTED_SEPARATE_SUITE',
    'env': {'api_key_empty': True, 'live': 'false', 'streaming': 'false', 'provider': 'mock',
            'default_workspace': str(base / 'default-workspace'), 'windows_user_environment_imported': False},
    'source_snapshot_before': snapshot(),
    'explicit_top_level_test_files': test_files,
    'test_results': [], 'deselected_nodes': [], 'windows_compile_nodes': [],
    'selected_test_count': None,
}
def save():
    prefix.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')

import pytest
class Evidence:
    def pytest_collection_finish(self, session):
        metadata['selected_test_count'] = len(session.items)
        metadata['selected_nodes'] = [item.nodeid for item in session.items]
        metadata['windows_compile_nodes'] = [item.nodeid for item in session.items if item.get_closest_marker('windows_compile')]
        assert not any(item.get_closest_marker('real_api') or item.get_closest_marker('e2e') for item in session.items)
        save()
    def pytest_deselected(self, items):
        metadata['deselected_nodes'].extend(item.nodeid for item in items)
    def pytest_runtest_logreport(self, report):
        if report.when == 'call' or report.outcome != 'passed':
            result = {'node': report.nodeid, 'when': report.when, 'outcome': report.outcome, 'seconds': round(report.duration, 5)}
            if report.outcome != 'passed':
                result['detail'] = str(report.longrepr)
            metadata['test_results'].append(result)
    def pytest_sessionfinish(self, session, exitstatus):
        reporter = session.config.pluginmanager.getplugin('terminalreporter')
        metadata['pytest_counts'] = {key: len(reporter.stats.get(key, [])) for key in ('passed', 'failed', 'error', 'skipped', 'deselected', 'warnings')}

args = test_files + ['-q', '-m', 'not real_api and not e2e', '--basetemp', str(base),
                     '--junitxml', str(prefix.with_suffix('.xml')), '-p', 'no:cacheprovider', '--tb=short']
metadata['pytest_arguments'] = args
save()
print(json.dumps({'status': 'STARTING', 'prefix': str(prefix), 'basetemp': str(base),
                  'top_level_test_files': len(test_files), 'source_snapshot_files': len(metadata['source_snapshot_before'])}), flush=True)
start = time.monotonic()
try:
    with prefix.with_suffix('.log').open('w', encoding='utf-8') as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            code = int(pytest.main(args, plugins=[Evidence()]))
    metadata['exit_code'] = code
except BaseException as exc:
    metadata['runner_error'] = type(exc).__name__ + ': ' + str(exc)
    metadata['exit_code'] = 2
finally:
    metadata['elapsed_seconds'] = round(time.monotonic() - start, 3)
    metadata['finished_at'] = datetime.datetime.now().astimezone().isoformat()
    after = snapshot()
    before = metadata['source_snapshot_before']
    metadata['source_snapshot_after'] = after
    metadata['changed_files'] = [key for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)]
    metadata['source_stable'] = not metadata['changed_files']
    metadata['windows_compile_results'] = [
        {'node': node, 'results': [result for result in metadata['test_results'] if result['node'] == node]}
        for node in metadata['windows_compile_nodes']]
    save()
print(json.dumps({key: metadata.get(key) for key in
                  ('exit_code', 'elapsed_seconds', 'pytest_counts', 'selected_test_count', 'source_stable', 'changed_files', 'runner_error')}),
      flush=True)
raise SystemExit(metadata['exit_code'])



