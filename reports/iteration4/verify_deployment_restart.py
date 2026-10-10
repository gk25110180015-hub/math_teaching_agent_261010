"""Compare stopped deployment backups with idle restarted workspaces, read-only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[2]


def fingerprint(path):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        connection.execute('BEGIN')
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        result = {}
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            rows = connection.execute('SELECT * FROM ' + quoted).fetchall()
            serial = sorted(json.dumps(row, ensure_ascii=False, sort_keys=True,
                default=lambda value: {'bytes_hex': value.hex()}) for row in rows)
            result[name] = {'rows': len(rows), 'sha256': hashlib.sha256(
                json.dumps(serial, ensure_ascii=False).encode('utf-8')).hexdigest()}
        assert connection.execute("SELECT count(*) FROM jobs WHERE status IN ('running','queued')").fetchone()[0] == 0
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deployment', type=Path)
    args = parser.parse_args()
    folder = args.deployment.resolve()
    assert folder.is_relative_to((ROOT / 'reports/iteration4').resolve())
    manifest = json.loads((folder / 'manifest.json').read_bytes())
    assert manifest['status'] == 'DEPLOYED'
    target = folder / 'restart-preservation.json'
    assert not target.exists(), 'Retain prior evidence; do not overwrite'
    report = {'at': datetime.now(timezone.utc).isoformat(), 'status': 'RUNNING',
        'api_calls': 0, 'database_mutations': 0, 'teacher_review': 'NOT_RUN',
        'expected_runtime_change_tables': ['worker_heartbeats'], 'workspaces': []}
    for index, relative in enumerate(('workspace/agent.db', 'workspace/iteration2-live/agent.db')):
        before = fingerprint(folder / f'before-{index}-agent.db')
        after = fingerprint(ROOT / relative)
        changes = [name for name in sorted(set(before) | set(after)) if before.get(name) != after.get(name)]
        unexpected = [name for name in changes if name != 'worker_heartbeats']
        report['workspaces'].append({'database': relative, 'before': before, 'after': after,
            'changed_tables': changes, 'unexpected_changes': unexpected,
            'stable_business_tables': sum(name != 'worker_heartbeats' and before.get(name) == after.get(name)
                for name in set(before) | set(after))})
    report['status'] = 'PASS' if all(not item['unexpected_changes'] for item in report['workspaces']) else 'NEEDS_REVIEW'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(target), 'workspaces': [
        {key: value for key, value in item.items() if key not in ('before', 'after')}
        for item in report['workspaces']]}, ensure_ascii=True))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
