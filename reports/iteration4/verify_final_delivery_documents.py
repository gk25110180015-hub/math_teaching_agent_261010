"""Validate final links/tables, unchanged deployed code/artifacts, and local service health."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,re,urllib.request,sqlite3
root=Path(__file__).resolve().parents[2]
out=root/'reports/iteration4'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
manifest=load(out/'delivery-manifest.json')
docs=[root/'README.md',out/'FINAL_ACCEPTANCE.md',out/'DELIVERABLES.md',out/'QUALITY_COMPARISON.md',
      out/'originals-recheck-20260924T080903/originals-preservation.md']+[Path(c['audit']) for c in manifest['cases']]
missing=[];malformed=[];link_count=0
for doc in docs:
    text=doc.read_text(encoding='utf-8')
    for m in re.finditer(r'\]\((?:<([^>]+)>|([^\s)]+))\)',text):
        target=m[1] or m[2]
        if target.startswith(('http:','https:','app:','#')):continue
        target=target.split('#',1)[0]
        if not target:continue
        dest=Path(re.sub(r':\d+$','',target))
        if not dest.is_absolute():dest=doc.parent/dest
        link_count+=1
        if not dest.exists():missing.append({'document':str(doc),'target':str(dest)})
    if doc.name in ('DELIVERABLES.md','FINAL_ACCEPTANCE.md','final-audit.md'):
        width=None
        for number,line in enumerate(text.splitlines(),1):
            if not line.startswith('|'):width=None;continue
            count=len(re.split(r'(?<!\\)\|',line))-2
            if width is None:width=count
            elif count!=width:malformed.append({'document':str(doc),'line':number,'expected':width,'actual':count})
suite=load(out/'local-full-20260923-230959-0068cbb3.json')
edge=load(out/'final-deployed-e2e/20260923-150959-2c67a2/source-hashes-after.json')
changed=[];checked={}
for snapshot in [suite['source_snapshot_before'],edge]:
    for name,expected in snapshot.items():
        observed=sha(root/name);checked[name]=observed
        if observed!=expected:changed.append(name)
artifact_checks=[]
for case in manifest['cases']:
    for name,artifact in case['artifacts'].items():
        artifact_checks.append({'case':case['case'],'name':name,'unchanged':sha(artifact['path'])==artifact['sha256']})
    with sqlite3.connect((root/'workspace/iteration2-live/agent.db').as_uri()+'?mode=ro',uri=True) as c:
        status,count=c.execute('SELECT status,request_count FROM runs WHERE id=?',(case['run_id'],)).fetchone()
        assert status=='AWAITING_USER_REVIEW' and count==case['request_count']
        assert not c.execute("SELECT 1 FROM jobs WHERE run_id=? AND status IN ('queued','running')",(case['run_id'],)).fetchone()
        assert not c.execute('SELECT 1 FROM reviews WHERE run_id=?',(case['run_id'],)).fetchone()
health={}
for port in [8765,8766]:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=5) as response:health[str(port)]=json.load(response)
passed=not(missing or malformed or changed) and all(x['unchanged'] for x in artifact_checks) and all(x['status']=='ok' and x['worker']['alive'] for x in health.values())
report={'at':datetime.now(timezone.utc).isoformat(),'status':'PASS' if passed else 'NOT_PASS',
 'checked_documents':[{ 'path':str(p),'sha256':sha(p)} for p in docs], 'checked_local_links':link_count,
 'missing_links':missing,'malformed_tables':malformed,'code_files_checked':len(checked),'code_changed':sorted(set(changed)),
 'current_artifacts':artifact_checks,'health':health,'model_calls':0,'teacher_reviews':'NOT_RUN',
 'new_full_pytest':'NOT_RUN; existing V7 evidence still matches source/test/script hashes'}
target=out/('final-delivery-document-check-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'links':link_count,'code_files':len(checked),'missing':missing,'tables':malformed,'report':str(target)},ensure_ascii=False))
raise SystemExit(0 if passed else 1)
