from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,zipfile
from math_agent.settings import Settings,PROJECT_ROOT
from math_agent.util import write_json
p=PROJECT_ROOT
secret=Settings().api_key.get_secret_value()
if not secret: raise SystemExit('Environment credential missing; value not printed')
needles=[secret.encode('utf-8'),secret.encode('utf-16-le')]
paths=[]
for case in ('smoke','CH01'):
    c=json.loads((p/'reports/iteration2/live-lectures'/case/'comparison.json').read_bytes())
    paths.extend((case,Path(a['path'])) for a in c['generated']['artifacts'] if a['name']=='source_bundle.zip')
paths.extend((f.parent.name,f) for f in sorted((p/'workspace/iteration2-delivery').glob('*/source_bundle-v2.zip')))
rows=[]
for case,path in paths:
    total=0;count=0;found=False
    with zipfile.ZipFile(path) as z:
        for member in z.infolist():
            if member.is_dir(): continue
            total+=member.file_size
            if member.file_size>100*1024*1024 or total>200*1024*1024: raise ValueError('Bounded archive scan size exceeded')
            data=z.read(member)
            count+=1
            found=found or any(n in data for n in needles)
    rows.append({'case':case,'zip_path':str(path),'zip_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'members_checked':count,'uncompressed_bytes':total,'exact_credential_found':found,'status':'FAIL' if found else 'PASS'})
report={'at':datetime.now(timezone.utc).isoformat(),'status':'PASS' if rows and not any(x['exact_credential_found'] for x in rows) else 'FAIL','archive_count':len(rows),'rows':rows,'credential_value':'NOT_RECORDED','scope':'Exact current environment credential UTF-8/UTF-16LE in decompressed members of selected delivered source ZIPs; not a scan of every historic or binary encoding.','api_requests':0,'teacher_visual_review':'NOT_RUN'}
write_json(p/'reports/iteration2/delivered-zip-secret-check-20260920-0434.json',report)
print(json.dumps({'status':report['status'],'archive_count':len(rows),'member_count':sum(r['members_checked'] for r in rows)}))
