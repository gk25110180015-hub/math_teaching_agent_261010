"""After deployment, run all 14 Edge scenarios with mock providers/Windows TeX.

Does not modify production source, environment persistence, or real task DBs.
Requires --run and refuses an undeployed feedback API/UI.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / 'reports/iteration4'
MODEL_EVIDENCE = ROOT / 'reports/iteration3/model-selection-e2e'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def source_hashes():
    files = []
    for base in (ROOT/'src/math_agent', ROOT/'tests', ROOT/'scripts', ROOT/'configs'):
        files.extend(path for path in base.rglob('*') if path.is_file()
                     and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo'))
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(files)}


def deployment_checks():
    required = {
        'src/math_agent/domain.py': ['class RecheckRequest(ExecuteRequest):'],
        'src/math_agent/service.py': ['RECHECK_FEEDBACK_UNSUPPORTED', "'feedback': req.feedback", 'def feedback_review(self, run):'],
        'src/math_agent/web/app.py': ['data:RecheckRequest'],
        'src/math_agent/pipeline.py': ['def _recheck_feedback(self, plan):', 'FeedbackReview(self,plan,units,feedback).evaluate()'],
        'src/math_agent/feedback_review.py': ['class FeedbackReview:', 'repair_unit_ids'],
        'src/math_agent/web/static/app.js': ['recheck-feedback', 'recheckFeedback', 'feedback?.value', 'renderFeedbackReview(run)', 'run.feedback_review]);'],
    }
    return {name: all(marker in (ROOT/name).read_text(encoding='utf-8') for marker in markers)
            for name, markers in required.items()}


def archive_databases(runtime, output):
    records = []
    for original in sorted(runtime.rglob('agent.db')):
        destination = output / 'databases' / original.relative_to(runtime)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(original.as_uri() + '?mode=ro', uri=True, timeout=5) as source:
            with sqlite3.connect(destination) as snapshot:
                source.backup(snapshot)
            tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            reviews = source.execute('SELECT count(*) FROM reviews').fetchone()[0] if 'reviews' in tables else 0
            events = source.execute("SELECT count(*) FROM events WHERE type='human.review'").fetchone()[0] if 'events' in tables else 0
            runs = [dict(zip(('status', 'count'), row)) for row in source.execute('SELECT status,count(*) FROM runs GROUP BY status')] if 'runs' in tables else []
        records.append({'original': str(original), 'archive': str(destination),
                        'archive_sha256': sha(destination), 'human_reviews': reviews,
                        'human_review_events': events, 'run_statuses': runs})
    return records


def archive_model_evidence(before, output):
    records = []
    names = {path.name for path in MODEL_EVIDENCE.iterdir() if path.is_dir()} if MODEL_EVIDENCE.is_dir() else set()
    for name in sorted(names - before):
        source = MODEL_EVIDENCE / name
        evidence = source / 'evidence.json'
        if not evidence.is_file():
            records.append({'original': str(source), 'status': 'INCOMPLETE_EVIDENCE'})
            continue
        data = json.loads(evidence.read_text(encoding='utf-8'))
        destination = output / 'model-selection' / name
        shutil.copytree(source, destination)
        files = []
        for original in sorted(source.rglob('*')):
            if original.is_file():
                relative = original.relative_to(source)
                identical = sha(original) == sha(destination/relative)
                files.append({'path': relative.as_posix(), 'sha256': sha(original), 'archive_matches': identical})
        records.append({'original': str(source), 'archive': str(destination),
                        'test_name': data.get('test_name'), 'model_http_transport': data.get('model_http_transport'),
                        'real_api': data.get('real_api'), 'files': files,
                        'status': 'PASS' if all(row['archive_matches'] for row in files) else 'HASH_MISMATCH'})
    return records


def stop_test_tree(process):
    if process.poll() is None:
        if os.name == 'nt':
            taskkill = Path(os.environ['SystemRoot'])/'System32/taskkill.exe'
            subprocess.run([str(taskkill), '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        else:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Explicitly run after production deployment is safe')
    parser.add_argument('--output-root', type=Path, default=REPORTS/'final-deployed-e2e')
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error('No tests started: pass --run only after the feedback deployment is complete')
    output_root = args.output_root.resolve()
    if not output_root.is_relative_to(REPORTS.resolve()) or output_root == REPORTS.resolve():
        parser.error('Output must be a child of reports/iteration4')
    if not 120 <= args.timeout_seconds <= 7200:
        parser.error('Timeout must be between 120 and 7200 seconds')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    output = output_root / stamp
    output.mkdir(parents=True, exist_ok=False)
    runtime = ROOT/'workspace/t'/('finaledge-' + stamp[-6:])
    if runtime.exists():
        raise FileExistsError('Refusing to reuse any existing pytest basetemp')
    before = source_hashes()
    checks = deployment_checks()
    result = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'STARTING',
        'expected_tests': 14, 'runtime': str(runtime), 'output': str(output), 'deployment_checks': checks,
        'real_api': 'NOT_RUN', 'teacher_mathematics_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
        'model_provider': 'MOCK_OR_HTTPX_MOCK_TRANSPORT', 'errors': []}
    save(output/'source-hashes-before.json', before)
    save(output/'result.json', result)
    if not all(checks.values()):
        result['status'] = 'NOT_RUN_DEPLOYMENT_MISSING'
        save(output/'result.json', result)
        print(json.dumps({'status': result['status'], 'output': str(output)}))
        return 2
    env = {name: value for name, value in os.environ.items()
           if not name.startswith('MATH_AGENT_') and name != 'OPENAI_API_KEY'}
    env.update(MATH_AGENT_API_KEY='', MATH_AGENT_DEEPSEEK_API_KEY='', MATH_AGENT_LIVE_API_ENABLED='false',
               MATH_AGENT_LLM_STREAMING='false', MATH_AGENT_E2E_EVIDENCE_ROOT=str(output),
               PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    model_before = {path.name for path in MODEL_EVIDENCE.iterdir() if path.is_dir()} if MODEL_EVIDENCE.is_dir() else set()
    command = [sys.executable, '-m', 'pytest', 'tests/e2e', '-q', '--basetemp', str(runtime),
               '--junitxml', str(output/'pytest.xml')]
    save(output/'invocation.json', {'command': command, 'environment': 'Credentials removed, models disabled, independent fixture workspaces',
        'note': 'Model-selection fixture uses dummy keys with MockTransport; it never contacts a model endpoint.'})
    print('EVIDENCE=' + str(output), flush=True)
    process = None
    started = time.monotonic()
    try:
        with (output/'pytest.log').open('x', encoding='utf-8') as stream:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            result['pytest_pid'] = process.pid
            result['pytest_exit_code'] = process.wait(timeout=args.timeout_seconds)
    except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        result['errors'].append({'stage': 'pytest', 'type': type(error).__name__, 'message': str(error)})
    finally:
        if process is not None:
            stop_test_tree(process)
        result['elapsed_seconds'] = round(time.monotonic()-started, 3)
        after = source_hashes()
        save(output/'source-hashes-after.json', after)
        result['source_and_tests_unchanged'] = before == after
        try:
            result['database_snapshots'] = archive_databases(runtime, output)
            result['human_reviews_zero'] = bool(result['database_snapshots']) and all(
                row['human_reviews'] == row['human_review_events'] == 0 for row in result['database_snapshots'])
        except (OSError, ValueError, sqlite3.Error) as error:
            result['errors'].append({'stage': 'database_archive', 'type': type(error).__name__, 'message': str(error)})
        try:
            result['model_evidence_archives'] = archive_model_evidence(model_before, output)
        except (OSError, ValueError) as error:
            result['errors'].append({'stage': 'model_evidence_archive', 'type': type(error).__name__, 'message': str(error)})
        try:
            suites = ElementTree.parse(output/'pytest.xml').getroot().findall('testsuite')
            result['junit'] = {name: sum(int(suite.get(name, 0)) for suite in suites)
                               for name in ('tests', 'failures', 'errors', 'skipped')}
            result['testcases'] = [value.attrib for suite in suites for value in suite.findall('testcase')]
        except (OSError, ValueError, ElementTree.ParseError) as error:
            result['errors'].append({'stage': 'junit', 'type': type(error).__name__, 'message': str(error)})
        junit = result.get('junit', {})
        passed = (not result['errors'] and result.get('pytest_exit_code') == 0 and before == after
            and result.get('human_reviews_zero') is True and junit.get('tests') == 14
            and all(junit.get(name) == 0 for name in ('failures', 'errors', 'skipped'))
            and len(result.get('model_evidence_archives', [])) == 5
            and all(row['status'] == 'PASS' for row in result.get('model_evidence_archives', [])))
        result.update(status='PASS' if passed else 'NOT_PASS', finished_at=datetime.now(timezone.utc).isoformat(),
            real_edge='PASS' if passed else 'SEE_INDIVIDUAL_TESTS',
            windows_compile='PASS_FOR_COMPILING_WORKFLOW_TESTS' if passed else 'SEE_INDIVIDUAL_TESTS')
        save(output/'result.json', result)
        print(json.dumps({'status': result['status'], 'junit': result.get('junit'),
                          'output': str(output), 'source_unchanged': before == after,
                          'human_reviews_zero': result.get('human_reviews_zero')}, ensure_ascii=True), flush=True)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
