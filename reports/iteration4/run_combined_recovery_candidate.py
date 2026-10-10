"""Stage an explicit merged candidate and test it without touching deployed files."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    return {p.relative_to(ROOT).as_posix(): sha(p)
            for folder in ('src/math_agent', 'tests', 'scripts', 'configs')
            for p in (ROOT/folder).rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('tests', nargs='+', help='Explicit test paths relative to tests/')
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    assert manifest_path.is_relative_to(REPORTS)
    manifest = json.loads(manifest_path.read_bytes())
    tag = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    output = REPORTS/'combined-recovery-validation'/tag
    package = ROOT/'workspace/t'/('cr' + tag[-6:])
    output.mkdir(parents=True, exist_ok=False)
    package.mkdir(parents=True, exist_ok=False)
    before = snapshot()
    for folder in ('src/math_agent', 'tests', 'configs', 'schemas', 'templates'):
        if (ROOT/folder).is_dir():
            shutil.copytree(ROOT/folder, package/folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copyfile(ROOT/'pyproject.toml', package/'pyproject.toml')
    for item in manifest['files']:
        original = (ROOT/item['source']).resolve()
        candidate = (REPORTS/item['candidate']).resolve()
        assert original.is_relative_to(ROOT) and candidate.is_relative_to(REPORTS)
        assert (sha(original) if original.exists() else None) == item['baseline_sha256']
        assert sha(candidate) == item['candidate_sha256']
        target = package/item['source']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate, target)
    for key in list(os.environ):
        if key.startswith('MATH_AGENT_') or key in ('OPENAI_API_KEY', 'PYTEST_ADDOPTS', 'PYTEST_PLUGINS'):
            os.environ.pop(key)
    os.environ.update(MATH_AGENT_API_KEY='', MATH_AGENT_DEEPSEEK_API_KEY='',
        MATH_AGENT_LIVE_API_ENABLED='false', MATH_AGENT_LLM_PROVIDER='mock',
        MATH_AGENT_WORKSPACE=str(package/'isolated-default-workspace'),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(package/'src'), str(package/'tests')]
    connections = []
    original_connect = socket.socket.connect

    def connect(instance, address):
        host = address[0] if isinstance(address, tuple) else None
        if host not in ('127.0.0.1', 'localhost', '::1'):
            connections.append(repr(address))
            raise RuntimeError('Offline candidate blocks external network')
        return original_connect(instance, address)

    socket.socket.connect = connect
    import pytest
    import math_agent.pipeline
    assert Path(math_agent.pipeline.__file__).resolve().is_relative_to(package)
    tests = [(package/'tests'/name).resolve() for name in args.tests]
    assert all(p.is_relative_to(package/'tests') and p.is_file() for p in tests)
    context = {'manifest': manifest, 'manifest_sha256': sha(manifest_path),
               'package': str(package), 'tests': [str(p) for p in tests], 'production_before': before}
    (output/'context.json').write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding='utf-8')
    print('EVIDENCE=' + str(output), flush=True)
    with (output/'pytest.log').open('x', encoding='utf-8') as log:
        with redirect_stdout(log), redirect_stderr(log):
            code = pytest.main([*[str(p) for p in tests], '-q', '-m', 'not windows_compile and not real_api and not e2e',
                '--basetemp', str(package/'t'), '--junitxml', str(output/'pytest.xml'), '-p', 'no:cacheprovider'])
    after = snapshot()
    result = {'status': 'PASS' if code == 0 and before == after and not connections else 'NOT_PASS',
        'pytest_exit_code': code, 'production_unchanged': before == after,
        'external_network_attempts': connections, 'real_api': 'NOT_RUN',
        'windows_compile': 'NOT_RUN', 'browser': 'NOT_RUN', 'teacher_review': 'NOT_RUN'}
    (output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print((output/'pytest.log').read_text(encoding='utf-8')[-8000:])
    print(json.dumps(result))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
