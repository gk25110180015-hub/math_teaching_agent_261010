"""Resume only the reported job via the app API, preserving approval and all evidence."""
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

RID='e53fd34585fb4bc9af2a85fd994d610a'
JOB='ccd8a766f61c454b931dd8fadb98c371'
ROOT=Path(__file__).resolve().parent


def snapshot(run):
    return {k:run.get(k) for k in ('id','status','stage','input_hash','approval','request_count','jobs','reviews')} | {
        'plan_hash':run['plan']['hash'], 'plan_revision':run['plan']['revision']}


def signature(path):
    with pdfplumber.open(path) as pdf:
        return [p.extract_text() or '' for p in pdf.pages]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    report_path=ROOT/'production-recovery.json'
    assert not report_path.exists(), 'Do not overwrite recovery evidence or repeat retry'
    baseline=json.loads((ROOT/'before/baseline.json').read_text(encoding='utf-8'))
    report={'started_at':now(),'run_id':RID,'job_id':JOB,'status':'RUNNING',
            'model_api_test':'NOT_RUN','teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'}
    write_json(report_path,report)
    try:
        with httpx.Client(base_url='http://127.0.0.1:8765',timeout=60,trust_env=False) as client:
            token=client.get('/api/session').json()['csrf_token']
            run=client.get('/api/runs/'+RID).raise_for_status().json()
            before=snapshot(run);report['before']=before
            assert run['approval']==baseline['approvals'][0], 'Original approval changed'
            assert run['input_hash']==baseline['input_hash']
            if args.resume:
                assert run['status']=='BLOCKED' and run['error']['code']=='QUALITY_BLOCKED'
                job=client.post('/api/runs/'+RID+'/retry',headers={'X-CSRF-Token':token},json={}).raise_for_status().json()
                assert job['id']==JOB
                report['retry_job']=job['id'];write_json(report_path,report)
            until=time.monotonic()+600;previous=None
            while run['status'] not in ('AWAITING_USER_REVIEW','COMPLETED','COMPLETED_WITH_WARNINGS'):
                run=client.get('/api/runs/'+RID).raise_for_status().json()
                state=(run['status'],run['stage'])
                if state!=previous:print(state,flush=True);previous=state
                if run['status'] in ('FAILED','BLOCKED'):
                    raise RuntimeError(str(run.get('error')))
                if time.monotonic()>until:raise TimeoutError('Task did not finish; state and outputs retained')
                time.sleep(1)
            report['after']=snapshot(run)
            assert run['approval']==before['approval'] and run['plan']['hash']==before['plan_hash']
            assert run['request_count']==before['request_count'], 'Unexpected external request'
            assert run['reviews']==before['reviews'], 'No teacher approvals may be submitted'
            report['old_files_changed']=[f['path'] for f in baseline['existing_files']
                if not Path(f['path']).is_file() or digest(Path(f['path']).read_bytes())!=f['sha256']]
            assert not report['old_files_changed']
            latest=json.loads((Path('workspace/runs')/RID/'latest_build.json').read_text(encoding='utf-8'))
            build=Path('workspace')/latest['storage_key'];report['build']=str(build.resolve())
            quality=json.loads((build/'quality_report.json').read_text(encoding='utf-8'))
            report['quality']={k:quality[k]['status'] for k in ('compile','fidelity','layout','math','policy')}
            assert quality['compile']['status']=='PASS' and quality['fidelity']['status']=='PASS'
            assert not any(i.get('severity')=='blocking' for i in quality['issues'])
            with sqlite3.connect(Path('workspace/agent.db').resolve().as_uri()+'?mode=ro',uri=True) as db:
                db.row_factory=sqlite3.Row
                rows=[dict(r) for r in db.execute('select * from artifacts where run_id=?',(RID,))
                      if r['storage_key'].startswith(latest['storage_key']+'/')]
            downloads=[]
            for row in rows:
                response=client.get('/api/artifacts/'+row['artifact_id']).raise_for_status()
                assert digest(response.content)==row['sha256']
                downloads.append({k:row[k] for k in ('artifact_id','name','sha256','storage_key')})
            report['downloads']=downloads
            report['download_count']=len(downloads)
            report['page_count']=quality['layout']['evidence']['page_count']
            write_json(report_path,report)
            clean=Path('workspace/q0926/delivery')
            assert not clean.exists()
            source=clean/'source';source.mkdir(parents=True)
            safe_extract_zip((build/'source_bundle.zip').read_bytes(),source)
            compile_result=TexCompiler().compile(source,'slides.tex',clean/'build',trusted=True)
            write_json(clean/'compile.json',compile_result)
            report['clean_compile']=compile_result['status']
            assert compile_result['status']=='PASS'
            original_pdf=next(Path('workspace')/r['storage_key'] for r in rows if r['name']=='slides.pdf')
            original=signature(original_pdf);rebuilt=signature(Path(compile_result['pdf_path']))
            report['clean_page_count']=len(rebuilt);report['clean_all_page_text_equal']=original==rebuilt
            assert len(rebuilt)==report['page_count'] and original==rebuilt
            report['status']='PASS'
    except Exception as exc:
        report['status']='FAIL';report['error']=str(exc)
        raise
    finally:
        report['finished_at']=now();write_json(report_path,report)
        print(json.dumps({k:report.get(k) for k in ('status','build','download_count','page_count','clean_compile','error')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
