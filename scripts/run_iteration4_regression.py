"""Collect or run all top-level local tests, preserving isolated iteration4 evidence.

Default is collection only. Use --run only after the product changes are merged.
Real API and browser E2E nodes are always excluded; Windows compile nodes remain.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import sys
import time
import uuid
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now().astimezone().isoformat()


def snapshot():
    paths = {ROOT / name for name in ('pyproject.toml', 'uv.lock', '.env.example')}
    paths.update((ROOT / 'tests').glob('test_*.py'))
    for folder in ('src', 'prompts', 'configs', 'templates', 'tests/fixtures', 'scripts'):
        directory = ROOT / folder
        if directory.exists():
            paths.update(path for path in directory.rglob('*')
                         if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if path.exists()}


def compile_purpose(node):
    for token, purpose in {
        'test_t17_cancel_actual_tex': 'EXPECTED_CANCEL',
        'test_t48_actual_failed_compile': 'EXPECTED_COMPILE_FAILURE',
        'test_t47_middle_overlay': 'EXPECTED_LAYOUT_FAILURE',
        'test_t52_actual_openout': 'EXPECTED_EXTERNAL_WRITE_REJECTION',
        'test_T31_broken_tabularx': 'EXPECTED_COMPILE_FAILURE',
        'test_actual_ch03_missing_glyph_before': 'BEFORE_AFTER_GLYPH_REGRESSION',
    }.items():
        if token in node:
            return purpose
    return 'READ_TEST_ASSERTIONS: Windows compile marker alone does not prove successful PDF compilation'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--collect-only', action='store_true', help='Collect and hash only (default).')
    mode.add_argument('--run', action='store_true', help='Execute the complete local suite after merging.')
    args = parser.parse_args()
    collect_only = not args.run
    os.chdir(ROOT)
    sys.dont_write_bytecode = True
    for key in list(os.environ):
        if key.startswith('MATH_AGENT_'):
            os.environ.pop(key, None)
    for key in ('PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'PYTEST_CURRENT_TEST'):
        os.environ.pop(key, None)
    unique = uuid.uuid4().hex[:8]
    basetemp = (ROOT / 'workspace/t' / ('i4' + unique)).resolve()
    assert basetemp.is_relative_to((ROOT / 'workspace/t').resolve()) and not basetemp.exists()
    report_dir = ROOT / 'reports/iteration4'
    report_dir.mkdir(parents=True, exist_ok=True)
    phase = 'collect' if collect_only else 'full'
    stamp = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
    prefix = report_dir / f'local-{phase}-{stamp}-{unique}'
    assert not any(prefix.with_suffix(suffix).exists() for suffix in ('.json', '.xml', '.log', '.md'))
    os.environ.update(MATH_AGENT_API_KEY='', MATH_AGENT_DEEPSEEK_API_KEY='',
        MATH_AGENT_LIVE_API_ENABLED='false', MATH_AGENT_LLM_STREAMING='false', MATH_AGENT_LLM_PROVIDER='mock',
        MATH_AGENT_WORKSPACE=str(basetemp / 'default-workspace'), PYTHONDONTWRITEBYTECODE='1',
        PYTHONIOENCODING='utf-8', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    test_files = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / 'tests').glob('test_*.py'))
    if not test_files:
        raise RuntimeError('No top-level tests/test_*.py found; refusing an empty suite.')
    metadata = {
        'started_at': now(), 'phase': phase, 'collection_only': collect_only,
        'status': 'COLLECTING' if collect_only else 'RUNNING',
        'suite_discovery': 'dynamic glob tests/test_*.py; nested tests/e2e not collected',
        'python': platform.python_version(), 'platform': platform.platform(),
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'explicit_top_level_test_files': test_files, 'basetemp': str(basetemp),
        'real_api': 'DISABLED_NOT_RUN', 'model_transport': 'MOCK_OR_FAKE_TRANSPORT',
        'windows_compile': 'COLLECTED_NOT_RUN' if collect_only else 'SEE_NODE_RESULTS',
        'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
        'browser_e2e': 'NOT_COLLECTED_NOT_HASHED_SEPARATE_SUITE',
        'environment': {'gpt6_api_key_empty': True, 'deepseek_api_key_empty': True,
            'live': 'false', 'streaming': 'false', 'provider': 'mock',
            'windows_user_environment_imported': False, 'pytest_plugin_autoload': False,
            'default_workspace': str(basetemp / 'default-workspace')},
        'network_guard': 'Current Python process blocks non-loopback socket.connect; child processes are not audited by this hook.',
        'blocked_network_targets': [], 'source_snapshot_before': snapshot(),
        'selected_nodes': [], 'deselected_nodes': [], 'test_results': [], 'windows_compile_nodes': [],
    }

    def save():
        prefix.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')

    def network_audit(event, details):
        if event != 'socket.connect' or not isinstance(details[1], tuple):
            return
        address = details[1]
        host = address[0].decode('ascii', errors='replace') if isinstance(address[0], bytes) else address[0]
        try:
            allowed = str(host).lower() == 'localhost' or ipaddress.ip_address(host).is_loopback
        except ValueError:
            allowed = False
        if not allowed:
            metadata['blocked_network_targets'].append({'host': str(host), 'port': address[1]})
            save()
            raise PermissionError('Offline regression blocks non-loopback socket connections.')

    sys.addaudithook(network_audit)
    import pytest

    class Evidence:
        def pytest_collection_finish(self, session):
            metadata['selected_nodes'] = [item.nodeid for item in session.items]
            metadata['selected_test_count'] = len(session.items)
            metadata['windows_compile_nodes'] = [item.nodeid for item in session.items
                                                  if item.get_closest_marker('windows_compile')]
            assert not any(item.get_closest_marker('real_api') or item.get_closest_marker('e2e')
                           for item in session.items)
            save()

        def pytest_deselected(self, items):
            metadata['deselected_nodes'].extend(item.nodeid for item in items)

        def pytest_runtest_logreport(self, report):
            if report.when == 'call' or report.outcome != 'passed':
                result = {'node': report.nodeid, 'when': report.when, 'outcome': report.outcome,
                          'seconds': round(report.duration, 5)}
                if report.outcome != 'passed':
                    result['detail'] = str(report.longrepr)
                metadata['test_results'].append(result)
                if report.outcome != 'passed' or len(metadata['test_results']) % 25 == 0:
                    save()

        def pytest_sessionfinish(self, session, exitstatus):
            reporter = session.config.pluginmanager.getplugin('terminalreporter')
            metadata['pytest_counts'] = {key: len(reporter.stats.get(key, []))
                                        for key in ('passed', 'failed', 'error', 'skipped', 'deselected', 'warnings')}

    pytest_args = test_files + ['-q', '-m', 'not real_api and not e2e', '--basetemp', str(basetemp),
        '--junitxml', str(prefix.with_suffix('.xml')), '-p', 'no:cacheprovider', '--tb=short']
    if collect_only:
        pytest_args.append('--collect-only')
    metadata['pytest_arguments'] = pytest_args
    save()
    print(json.dumps({'status': metadata['status'], 'prefix': str(prefix), 'basetemp': str(basetemp),
        'top_level_test_files': len(test_files)}, ensure_ascii=False), flush=True)
    started = time.monotonic()
    try:
        with prefix.with_suffix('.log').open('w', encoding='utf-8', buffering=1) as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                metadata['pytest_exit_code'] = int(pytest.main(pytest_args, plugins=[Evidence()]))
    except BaseException as exc:
        metadata['runner_error'] = type(exc).__name__ + ': ' + str(exc)
        metadata['pytest_exit_code'] = 2
    finally:
        metadata['elapsed_seconds'] = round(time.monotonic() - started, 3)
        metadata['finished_at'] = now()
        before, after = metadata['source_snapshot_before'], snapshot()
        metadata['source_snapshot_after'] = after
        metadata['changed_files'] = [key for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)]
        metadata['source_stable'] = not metadata['changed_files']
        metadata['windows_compile_results'] = [{'node': node, 'purpose': compile_purpose(node),
            'results': [result for result in metadata['test_results'] if result['node'] == node]}
            for node in metadata['windows_compile_nodes']]
        metadata['exit_code'] = metadata['pytest_exit_code'] or (2 if not metadata['source_stable'] else 0)
        if metadata['exit_code']:
            metadata['status'] = 'FAILED_OR_SOURCE_CHANGED'
        else:
            metadata['status'] = 'COLLECTED_NOT_RUN' if collect_only else 'LOCAL_SUITE_PASS'
        if prefix.with_suffix('.xml').exists():
            try:
                junit = ET.parse(prefix.with_suffix('.xml')).getroot()
                metadata['junit_suites'] = [dict(suite.attrib) for suite in junit.iter('testsuite')]
            except ET.ParseError as exc:
                metadata['junit_parse_error'] = str(exc)
        save()
        counts = metadata.get('pytest_counts', {})
        lines = ['# Iteration4 本地测试证据', '', f"状态：**{metadata['status']}**。开始 {metadata['started_at']}，结束 {metadata['finished_at']}。", '',
            f"动态收集 {len(test_files)} 个顶层测试文件，选中 {metadata.get('selected_test_count', 0)} 项，"
            f"排除 {len(metadata['deselected_nodes'])} 项真实 API/E2E 测试。", '',
            '本次只收集，未执行测试；Windows 编译同样 NOT_RUN。' if collect_only else
            f"pytest 结果：{counts.get('passed', 0)} passed，{counts.get('failed', 0)} failed，"
            f"{counts.get('error', 0)} errors，{counts.get('skipped', 0)} skipped。", '',
            f"前后 SHA 覆盖 {len(before)} 个源文件/提示词/配置/模板/脚本/测试/锁文件；source_stable={metadata['source_stable']}。", '',
            '两家模型密钥清空，live=false、streaming=false、provider=mock；不导入 Windows User 环境。'
            '新建隔离测试目录，保留失败日志与产物；没有恢复真实任务。真实 API、浏览器 E2E、教师数学与人工视觉验收均 NOT_RUN。', '',
            f"Windows 编译标记节点 {len(metadata['windows_compile_nodes'])} 个。标记可能包含预期失败、取消或诊断探针；"
            '测试通过不等于每个节点都成功生成 PDF。', '', '|节点|用途|实际结果|', '|---|---|---|']
        for item in metadata['windows_compile_results']:
            outcome = ', '.join(result['when'] + ':' + result['outcome'] for result in item['results']) or 'NOT_RUN'
            lines.append(f"|{item['node']}|{item['purpose']}|{outcome}|")
        lines += ['', f"证据：[日志]({prefix.name}.log)、[JUnit]({prefix.name}.xml)、[节点与前后 SHA]({prefix.name}.json)。", '',
                  f"保留测试目录：`{basetemp}`。不同轮次/专项不累计为独立测试总数。"]
        prefix.with_suffix('.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({key: metadata.get(key) for key in ('status', 'exit_code', 'pytest_counts',
        'selected_test_count', 'source_stable', 'changed_files', 'elapsed_seconds', 'runner_error')}, ensure_ascii=False), flush=True)
    return metadata['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
