"""One-shot checked deployment; only run after both local services are stopped."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'reports/iteration4'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def checked_path(base, relative):
    path = (base / relative).resolve()
    assert path.is_relative_to(base.resolve()), 'Manifest path escapes permitted root'
    assert path != base.resolve(), 'Manifest must name a file'
    return path


def main():
    entries = json.loads((EVIDENCE / 'recheck-feedback-api-ui-manifest.json').read_bytes())['files']
    pipe = json.loads((EVIDENCE / 'recheck-feedback-pipeline-manifest.json').read_bytes())
    entries += [{'source': 'src/math_agent/pipeline.py',
        'candidate': 'recheck-feedback-pipeline.candidate.py',
        'baseline_sha256': pipe['base_production_raw_sha256'],
        'candidate_sha256': pipe['artifacts']['recheck-feedback-pipeline.candidate.py']['raw_sha256']}]
    benchmark = EVIDENCE / '待合并/benchmark-recheck-manifest.json'
    assert benchmark.is_file(), 'Wait for the reviewed benchmark candidate manifest'
    entries += [dict(entry, candidate='待合并/' + entry['candidate'])
        for entry in json.loads(benchmark.read_bytes())['files']]
    guard_manifest = EVIDENCE / 'review-evidence-attribution-manifest.json'
    assert guard_manifest.is_file(), 'Wait for the reviewed attribution guard candidate'
    guard = json.loads(guard_manifest.read_bytes())
    assert guard.get('status') == 'READY_FOR_REVIEWED_DEPLOYMENT', 'Attribution candidate review is not complete'
    by_source = {entry['source']: entry for entry in entries}
    for entry in guard['files']:
        by_source[entry['source']] = entry
    entries = list(by_source.values())
    for entry in entries:
        source = checked_path(ROOT, entry['source'])
        candidate = checked_path(EVIDENCE, entry['candidate'])
        if entry['baseline_sha256'] is None:
            assert not source.exists(), entry['source'] + ' unexpectedly exists'
        else:
            assert sha(source) == entry['baseline_sha256'], entry['source'] + ' changed'
        assert sha(candidate) == entry['candidate_sha256'], entry['candidate'] + ' changed'
    databases = [ROOT / 'workspace/agent.db', ROOT / 'workspace/iteration2-live/agent.db']
    for db in databases:
        assert db.is_file(), str(db)
        assert not (db.parent / 'runtime/local-processes.json').exists(), 'Stop registered local processes first'
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as connection:
            assert connection.execute("SELECT count(*) FROM jobs WHERE status IN ('running','queued')").fetchone()[0] == 0, 'Active jobs'
    folder = EVIDENCE / ('deploy-feedback-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6])
    folder.mkdir(exist_ok=False)
    for entry in entries:
        target = folder / entry['source']
        target.parent.mkdir(parents=True, exist_ok=True)
        if entry['baseline_sha256'] is not None:
            shutil.copyfile(ROOT / entry['source'], target)
    for number, db in enumerate(databases):
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as connection:
            with sqlite3.connect(folder / f'before-{number}-agent.db') as backup:
                connection.backup(backup)
    result = {'status': 'PREPARED', 'files': entries, 'databases': [str(db) for db in databases],
        'teacher_review': 'NOT_PERFORMED'}
    save(folder / 'manifest.json', result)
    try:
        for entry in entries:
            target = checked_path(ROOT, entry['source'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(checked_path(EVIDENCE, entry['candidate']).read_bytes())
        for entry in entries:
            assert sha(ROOT / entry['source']) == entry['candidate_sha256']
        result['status'] = 'DEPLOYED'
    except BaseException as exc:
        for entry in entries:
            target = checked_path(ROOT, entry['source'])
            if entry['baseline_sha256'] is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes((folder / entry['source']).read_bytes())
        result.update(status='ROLLED_BACK', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save(folder / 'manifest.json', result)
        print(json.dumps({'folder': str(folder), **result}, ensure_ascii=True))


if __name__ == '__main__':
    main()
