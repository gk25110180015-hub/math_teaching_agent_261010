"""Apply this requested layout fix to the existing approved run; preserve every old artifact."""
import argparse
import json
from pathlib import Path
import sqlite3
import time

import httpx
import pdfplumber
from math_agent.compiler import TexCompiler
from math_agent.parsing import safe_extract_zip
from math_agent.util import digest, now, write_json

RID='0d14ccca52404f7585446dc6f9535ef9'
folder=Path(__file__).resolve().parent
root=folder.parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
assert args.execute,'Explicit execution flag required'
target=folder/'production.json'
assert not target.exists(),'Do not repeat a completed or interrupted recheck; inspect saved job first'
report={'started_at':now(),'run_id':RID,'status':'RUNNING','model_api':'NOT_RUN',
        'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'}
write_json(target,report)
def texts(path):
    with pdfplumber.open(path) as pdf:return [page.extract_text() or '' for page in pdf.pages]
def stored_artifacts():
    with sqlite3.connect((root/'workspace/agent.db').resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        return [dict(row) for row in db.execute('select * from artifacts where run_id=?',(RID,))]
try:
    with httpx.Client(base_url='http://127.0.0.1:8765',timeout=60,trust_env=False) as client:
        token=client.get('/api/session').raise_for_status().json()['csrf_token']
        before=client.get('/api/runs/'+RID).raise_for_status().json()
        assert before['status']=='AWAITING_USER_REVIEW'
        old_artifacts=stored_artifacts()
        report['before']={k:before[k] for k in ('status','input_hash','approval','request_count','reviews')}
        report['plan_hash']=before['plan']['hash']
        job=client.post('/api/runs/'+RID+'/recheck',headers={'X-CSRF-Token':token},json={
            'expected_plan_revision':before['plan']['revision'],'expected_plan_hash':before['plan']['hash'],
            'idempotency_key':'beamer-layout-fix-20260927','feedback':'','feedback_source':'user'}).raise_for_status().json()
        report['job_id']=job['id'];write_json(target,report)
        deadline=time.monotonic()+1200;last=None
        while True:
            run=client.get('/api/runs/'+RID).raise_for_status().json()
            state=(run['status'],run['stage'])
            if state!=last:print(state,flush=True);last=state
            if run['status']=='AWAITING_USER_REVIEW':break
            if run['status'] in ('BLOCKED','FAILED','CANCELLED'):raise RuntimeError(str(run.get('error')))
            if time.monotonic()>deadline:raise TimeoutError('Build still running; resume the existing saved job')
            time.sleep(2)
        assert run['approval']==before['approval'] and run['plan']==before['plan']
        assert run['input_hash']==before['input_hash'] and run['request_count']==before['request_count']==0
        assert run['reviews']==before['reviews']==[]
        report['old_files_changed']=[a['artifact_id'] for a in old_artifacts
            if not (root/'workspace'/a['storage_key']).is_file() or digest((root/'workspace'/a['storage_key']).read_bytes())!=a['sha256']]
        assert not report['old_files_changed']
        report['old_artifact_count']=len(old_artifacts)
        artifacts=[a for a in stored_artifacts() if a['status']!='superseded']
        downloads=[]
        for artifact in artifacts:
            data=client.get('/api/artifacts/'+artifact['artifact_id']).raise_for_status().content
            assert digest(data)==artifact['sha256']
            downloads.append({k:artifact[k] for k in ('artifact_id','name','sha256','storage_key')})
        report['downloads']=downloads
        quality_file=next(a for a in artifacts if a['name']=='quality_report.json')
        quality=json.loads((root/'workspace'/quality_file['storage_key']).read_text(encoding='utf-8'))
        report['quality']={k:quality[k]['status'] for k in ('compile','fidelity','layout','policy','math')}
        assert not any(i.get('severity')=='blocking' for i in quality['issues'])
        assert quality['compile']['status']==quality['fidelity']['status']=='PASS'
        report['page_count']=quality['layout']['evidence']['page_count']
        frame_file=next(a for a in artifacts if a['name']=='frame_plan.json')
        frames=json.loads((root/'workspace'/frame_file['storage_key']).read_text(encoding='utf-8'))
        report['logical_frames']=len(frames)
        assert not any(f['section_id']=='S02' for f in frames)
        assert len(frames)==134 and report['page_count']==178
        report['after']={k:run[k] for k in ('status','input_hash','approval','request_count','reviews')}
        write_json(target,report)
        bundle=next(a for a in artifacts if a['name']=='source_bundle.zip')
        pdf=next(a for a in artifacts if a['name']=='slides.pdf')
        clean=root/'workspace/q0927/delivery'
        assert not clean.exists();(clean/'source').mkdir(parents=True)
        safe_extract_zip(client.get('/api/artifacts/'+bundle['artifact_id']).raise_for_status().content,clean/'source')
        compiled=TexCompiler().compile(clean/'source','slides.tex',clean/'build',trusted=True)
        write_json(clean/'compile.json',compiled);report['clean_compile']=compiled['status']
        assert compiled['status']=='PASS'
        original=texts(root/'workspace'/pdf['storage_key']);rebuilt=texts(compiled['pdf_path'])
        report['clean_all_page_text_equal']=original==rebuilt
        assert original==rebuilt and len(original)==178
        report['status']='PASS'
except Exception as exc:
    report.update(status='FAIL',error=str(exc));raise
finally:
    report['finished_at']=now();write_json(target,report)
    print(json.dumps({k:report.get(k) for k in ('status','job_id','logical_frames','page_count','clean_compile','error')},ensure_ascii=False),flush=True)
