"""Deploy reviewed feedback receipts only after both workspaces are idle/stopped."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / 'reports/iteration4'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def within(base, relative):
    target = (base / relative).resolve()
    assert target.is_relative_to(base.resolve()) and target != base.resolve()
    return target


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    entries = []
    manifests = []
    for name in ('feedback-assessment-manifest.json', 'feedback-receipts-api-ui-manifest.json'):
        path = REPORTS / name
        manifest = json.loads(path.read_bytes())
        assert manifest['status'] == 'READY_FOR_REVIEWED_DEPLOYMENT', name + ' is not ready'
        entries.extend(manifest['files'])
        manifests.append({'path': name, 'sha256': sha(path)})
    targets = [within(ROOT, item['source']) for item in entries]
    assert len({str(path).casefold() for path in targets}) == len(targets), 'Conflicting manifest targets'
    for item, target in zip(entries, targets):
        assert target.is_relative_to((ROOT / 'src/math_agent').resolve()), 'Unexpected deployment scope'
        if item['baseline_sha256'] is None:
            assert not target.exists(), item['source'] + ' unexpectedly exists'
        else:
            assert sha(target) == item['baseline_sha256'], item['source'] + ' baseline changed'
        assert sha(within(REPORTS, item['candidate'])) == item['candidate_sha256']
    databases = [ROOT / 'workspace/agent.db', ROOT / 'workspace/iteration2-live/agent.db']
    for db in databases:
        assert db.is_file()
        assert not (db.parent / 'runtime/local-processes.json').exists(), 'Stop managed processes first'
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as source:
            assert source.execute("SELECT count(*) FROM jobs WHERE status IN ('running','queued')").fetchone()[0] == 0, 'Active jobs remain'
    folder = REPORTS / ('deploy-feedback-receipts-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6])
    folder.mkdir(exist_ok=False)
    for item, target in zip(entries, targets):
        if item['baseline_sha256'] is not None:
            backup = within(folder, item['source']); backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, backup)
    for index, db in enumerate(databases):
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as source:
            with sqlite3.connect(folder / f'before-{index}-agent.db') as backup:
                source.backup(backup)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'PREPARED',
        'candidate_manifests': manifests, 'files': entries, 'teacher_review': 'NOT_PERFORMED'}
    save(folder / 'manifest.json', report)
    try:
        for item, target in zip(entries, targets):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(within(REPORTS, item['candidate']).read_bytes())
            assert sha(target) == item['candidate_sha256']
        report['status'] = 'DEPLOYED'
    except BaseException as exc:
        for item, target in zip(entries, targets):
            if item['baseline_sha256'] is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(within(folder, item['source']).read_bytes())
        report.update(status='ROLLED_BACK', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save(folder / 'manifest.json', report)
        print(json.dumps({'folder': str(folder), 'status': report['status'], 'file_count': len(entries)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
