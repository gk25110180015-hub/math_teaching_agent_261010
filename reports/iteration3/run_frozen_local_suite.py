"""Frozen top-level local regression; no User-env import or real API access."""
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
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.dont_write_bytecode = True
for key in list(os.environ):
    if key.startswith('MATH_AGENT_'):
        os.environ.pop(key, None)
tag = datetime.datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
base = ROOT / 'workspace' / 't' / ('mmf' + uuid.uuid4().hex[:8])
assert base.is_relative_to(ROOT / 'workspace' / 't') and not base.exists()
prefix = ROOT / 'reports' / 'iteration3' / ('local-final-' + tag)
assert not prefix.with_suffix('.json').exists()
os.environ.update(MATH_AGENT_API_KEY='', MATH_AGENT_DEEPSEEK_API_KEY='',
    MATH_AGENT_LIVE_API_ENABLED='false', MATH_AGENT_LLM_STREAMING='false', MATH_AGENT_LLM_PROVIDER='mock',
    MATH_AGENT_WORKSPACE=str(base / 'default-workspace'), PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
test_files = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'tests').glob('test_*.py'))


def snapshot():
    paths = {ROOT / name for name in ('pyproject.toml', 'uv.lock', '.env.example',
        'scripts/Configure-LiveApi.py', 'scripts/Common-Windows.ps1', 'scripts/Test-Windows.ps1',
        'scripts/verify_model_capabilities.py')}
    paths.update((ROOT / 'tests').glob('test_*.py'))
    for directory in ('src', 'tests/fixtures', 'configs', 'templates'):
        root = ROOT / directory
        if root.exists():
            paths.update(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def compile_purpose(node):
    for token, purpose in {
        'test_t17_cancel_actual_tex': 'EXPECTED_CANCEL: infinite-loop compiler is cancelled; unrelated process survives',
        'test_t48_actual_failed_compile': 'EXPECTED_COMPILE_FAIL: undefined-command diagnostics are preserved',
        'test_t47_middle_overlay': 'EXPECTED_LAYOUT_FAIL: all overlays render; middle-page overflow blocks acceptance',
        'test_t52_actual_openout': 'EXPECTED_PROCESS_FAIL: TeX external write is denied',
        'test_T31_broken_tabularx': 'EXPECTED_COMPILE_FAIL: broken source location and original unit are preserved',
        'test_actual_ch03_missing_glyph_before': 'BEFORE_AFTER_REGRESSION: original glyph defect and corrected compile both inspected',
    }.items():
        if token in node:
            return purpose
    return 'COMPILE_AND_ASSERT_SUCCESS: actual Windows XeLaTeX plus test-specific artifact assertions'


metadata = {
    'started_at': datetime.datetime.now().astimezone().isoformat(),
    'suite': 'All top-level tests/test_*.py after three-model routing, UI selection and environment/CLI changes',
    'python': platform.python_version(), 'platform': platform.platform(),
    'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'freeze_basis': 'Root confirmed product freeze after 60 targeted and overlapping 102 provider tests',
    'basetemp': base.relative_to(ROOT).as_posix(),
    'real_api': 'DISABLED_NOT_RUN', 'provider': 'MOCK_OR_FAKE_TRANSPORT',
    'teacher_visual_review': 'NOT_RUN', 'teacher_math_review': 'NOT_RUN',
    'e2e_directory': 'NOT_COLLECTED_NOT_HASHED_SEPARATE_SUITE',
    'env': {'gpt6_api_key_empty': True, 'deepseek_api_key_empty': True, 'live': 'false',
            'streaming': 'false', 'provider': 'mock', 'default_workspace': str(base / 'default-workspace'),
            'windows_user_environment_imported': False},
    'source_snapshot_before': snapshot(), 'explicit_top_level_test_files': test_files,
    'test_results': [], 'deselected_nodes': [], 'windows_compile_nodes': [], 'selected_test_count': None,
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


args = test_files + ['-q', '-m', 'not real_api', '--basetemp', str(base),
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
        {'node': node, 'purpose': compile_purpose(node),
         'results': [result for result in metadata['test_results'] if result['node'] == node]}
        for node in metadata['windows_compile_nodes']]
    if prefix.with_suffix('.xml').exists():
        junit = ET.parse(prefix.with_suffix('.xml')).getroot()
        metadata['junit_suites'] = [dict(suite.attrib) for suite in junit.iter('testsuite')]
        metadata['junit_windows_compile_nodes'] = [
            {'classname': case.get('classname'), 'name': case.get('name'), 'seconds': case.get('time'),
             'result': 'failed' if case.find('failure') is not None else 'error' if case.find('error') is not None
                       else 'skipped' if case.find('skipped') is not None else 'passed'}
            for case in junit.iter('testcase')
            if any(node.split('::')[-1] == case.get('name') for node in metadata['windows_compile_nodes'])]
    save()
    counts = metadata.get('pytest_counts', {})
    lines = ['# 最终顶层本地回归', '',
        f"开始：{metadata['started_at']}；结束：{metadata['finished_at']}。", '',
        f"结果：{counts.get('passed', 0)} passed，{counts.get('failed', 0)} failed，{counts.get('error', 0)} errors，"
        f"{counts.get('skipped', 0)} skipped，{counts.get('deselected', 0)} deselected，{counts.get('warnings', 0)} warnings。", '',
        f"显式收集 {len(test_files)} 个顶层测试文件；前后 SHA 覆盖 {len(before)} 个源文件/测试/配置/模板/锁文件，"
        f"source_stable={metadata['source_stable']}；changed_files={metadata['changed_files']}。", '',
        '两家 API 密钥显式为空，live=false、streaming=false、provider=mock；未导入 Windows User 环境。'
        '默认与测试工作区均为新建隔离目录。真实 API 未执行，E2E 目录未收集且未纳入冻结哈希，浏览器另测。'
        '教师数学与人工视觉验收均未执行；没有恢复旧讲义任务或修改其预算。', '',
        f"Windows 标记节点 {len(metadata['windows_compile_nodes'])} 个，下表同时记录 pytest call 与 JUnit 结果。"
        '故意失败、取消、安全限制及排版失败探针通过，表示恢复/诊断符合预期，不表示 PDF 编译成功。', '',
        '|节点|用途|call结果|', '|---|---|---|']
    for result in metadata['windows_compile_results']:
        outcomes = ', '.join(item['when'] + ':' + item['outcome'] for item in result['results']) or 'NOT_RUN'
        lines.append(f"|{result['node']}|{result['purpose']}|{outcomes}|")
    lines += ['', '真实 API 排除节点：', ''] + ['- `' + node + '`' for node in metadata['deselected_nodes']]
    lines += ['', f"证据：[日志]({prefix.name}.log)、[JUnit]({prefix.name}.xml)、[环境、逐节点和前后 SHA]({prefix.name}.json)。",
              '', f"隔离测试目录：`{metadata['basetemp']}`。保留全部测试产物及故意失败日志；计数不与此前定向回归相加。"]
    prefix.with_suffix('.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(json.dumps({key: metadata.get(key) for key in
    ('exit_code', 'elapsed_seconds', 'pytest_counts', 'selected_test_count', 'source_stable', 'changed_files', 'runner_error')}), flush=True)
raise SystemExit(metadata['exit_code'])
