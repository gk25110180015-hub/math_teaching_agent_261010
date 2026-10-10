"""Scan changed text/DB files plus the actual delivered ZIP members, without printing secrets."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
import zipfile
from math_agent.settings import PROJECT_ROOT, Settings

root = PROJECT_ROOT
settings = Settings()
credentials = {'gpt6': settings.api_key.get_secret_value(), 'deepseek': settings.deepseek_api_key.get_secret_value()}
assert all(credentials.values()), 'Both environment credentials required; no value printed'
needles = [value.encode(encoding) for value in credentials.values() for encoding in ('utf-8','utf-16-le','utf-16-be')]
cutoff = datetime(2026, 9, 23, 15, 0, tzinfo=timezone.utc).timestamp()
baseline = root / 'reports/iteration4/secret-storage-20260923T1513.json'
assert json.loads(baseline.read_bytes())['status'] == 'PASS'
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
target = root / 'reports/iteration4' / ('final-secret-delta-' + stamp + '.json')
report = {'status': 'RUNNING', 'started_at': datetime.now(timezone.utc).isoformat(),
    'baseline_report': str(baseline), 'baseline_sha256': hashlib.sha256(baseline.read_bytes()).hexdigest(),
    'cutoff_utc': '2026-09-23T15:00:00+00:00', 'files_checked': 0, 'matching_paths': [], 'unreadable': [],
    'archives': [], 'credential_profiles': list(credentials), 'credential_value': 'NOT_RECORDED', 'model_calls': 0,
    'scope': 'Selected project text/TeX/DB/environment files with mtime since cutoff, plus decompressed members of current three lecture ZIPs and all six delivered Beamer v2 ZIPs. Baseline covers prior selected files; no claim about all binary encodings or other historical ZIPs.'}
extensions = set(json.loads(baseline.read_bytes())['extensions'])
def persist():
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
persist()
print(json.dumps({'status':'RUNNING','report':str(target)},ensure_ascii=False),flush=True)
import atexit
atexit.register(persist)
def matches_stream(stream):
    tail = b''
    while chunk := stream.read(1024 * 1024):
        data = tail + chunk
        if any(needle in data for needle in needles): return True
        tail = data[-max(map(len, needles)):]
    return False
for directory, dirs, names in os.walk(root, onerror=lambda e: report['unreadable'].append(str(e.filename))):
    dirs[:] = [d for d in dirs if d not in {'.venv','.git','__pycache__','.pytest_cache','node_modules'}]
    for name in names:
        path = Path(directory) / name
        if path.suffix.lower() not in extensions and not name.lower().startswith('.env.'): continue
        try:
            if path.stat().st_mtime < cutoff: continue
            with path.open('rb') as stream:
                if matches_stream(stream): report['matching_paths'].append(str(path.relative_to(root)))
            report['files_checked'] += 1
        except OSError:
            report['unreadable'].append(str(path))
archives = []
workspace = root / 'workspace/iteration2-live'
with sqlite3.connect((workspace / 'agent.db').as_uri() + '?mode=ro', uri=True) as c:
    c.row_factory = sqlite3.Row
    for case, rid in [('CH01','05748ab6260c40989a560a98e1e2065a'),('CH02','fd6736af6ef14be3839e019e86ca1e5c'),('CH03','a45be503af594ce8aae0bb1e4c30184b')]:
        assert c.execute('SELECT status FROM runs WHERE id=?',(rid,)).fetchone()[0] == 'AWAITING_USER_REVIEW'
        row = c.execute("SELECT * FROM artifacts WHERE run_id=? AND name='source_bundle.zip' AND status!='superseded' ORDER BY created_at DESC,rowid DESC LIMIT 1",(rid,)).fetchone()
        archives.append((case, workspace / row['storage_key'], row['sha256']))
for path in sorted((root / 'workspace/iteration2-delivery').glob('*/source_bundle-v2.zip')):
    archives.append((path.parent.name, path, hashlib.sha256(path.read_bytes()).hexdigest()))
assert len(archives) == 9
for case, path, expected in archives:
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    members, total = 0, 0
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        for member in archive.infolist():
            if member.is_dir(): continue
            total += member.file_size
            assert member.file_size <= 100 * 1024**2 and total <= 200 * 1024**2
            with archive.open(member) as stream:
                if matches_stream(stream): report['matching_paths'].append(str(path.relative_to(root)) + '::' + member.filename)
            members += 1
    report['archives'].append({'case': case, 'path': str(path), 'sha256': expected, 'members': members})
report['status'] = 'FAIL' if report['matching_paths'] else 'INCOMPLETE' if report['unreadable'] else 'PASS'
report['finished_at'] = datetime.now(timezone.utc).isoformat()
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'files_checked':report['files_checked'],'archives':len(archives),'report':str(target)},ensure_ascii=False))
raise SystemExit(0 if report['status']=='PASS' else 1)
