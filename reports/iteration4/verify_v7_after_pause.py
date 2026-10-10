"""Check current code against V7 test evidence and retain the previous launcher records."""
from datetime import datetime,timezone
import hashlib,json,shutil,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
reports=root/'reports/iteration4'
out=reports/('restart-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
out.mkdir(exist_ok=False)
suite=json.loads((reports/'local-full-20260923-230959-0068cbb3.json').read_bytes())
edge_dir=reports/'final-deployed-e2e/20260923-150959-2c67a2'
edge=json.loads((edge_dir/'result.json').read_bytes())
assert suite['status']=='LOCAL_SUITE_PASS' and edge['status']=='PASS'
checked={};changed=[]
for snapshot in [suite['source_snapshot_before'],json.loads((edge_dir/'source-hashes-after.json').read_bytes())]:
    for name,expected in snapshot.items():
        file=root/name
        actual=hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
        checked[name]=actual
        if actual!=expected:changed.append(name)
assert not changed,changed
for i,ws in enumerate([root/'workspace',root/'workspace/iteration2-live']):
    state=ws/'runtime/local-processes.json'
    if state.exists():shutil.copyfile(state,out/f'previous-launcher-{i}.json')
    with sqlite3.connect((ws/'agent.db').as_uri()+'?mode=ro',uri=True) as source:
        assert source.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]==0
        with sqlite3.connect(out/f'before-{i}-agent.db') as dest:source.backup(dest)
result={'at':datetime.now(timezone.utc).isoformat(),'status':'PASS','checked_files':len(checked),
        'changed':changed,'local_tests':1118,'edge_tests':14,'new_tests':'NOT_RUN',
        'source_hashes':checked,'reason':'Both services exited during quota pause; CH01 blocked after all-provider timeouts; no running jobs.'}
(out/'code-and-backup.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','checked_files':len(checked),'report':str(out)},ensure_ascii=False))
