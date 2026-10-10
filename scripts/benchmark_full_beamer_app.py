"""One full original CH03 through Service/Worker and in-process download API.

No model requests, no web server port, no teacher-review submission. All originals
remain read-only; report and runtime paths are separate from direct-converter runs.
"""
from __future__ import annotations

import hashlib
import argparse
import io
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def sha(data):return hashlib.sha256(data).hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def code_hashes():
    return {p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sorted((ROOT/'src').rglob('*.py'))}


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--label',default='',choices=['','v2'])
    args=cli.parse_args()
    suffix='-'+args.label if args.label else ''
    # Explicitly disable live capability in this process; never read credentials.
    os.environ.pop('MATH_AGENT_API_KEY',None)
    os.environ['MATH_AGENT_LIVE_API_ENABLED']='false'
    os.environ['MATH_AGENT_LLM_STREAMING']='false'
    report_dir=ROOT/('reports/iteration2/full_beamer_app'+suffix)
    report_dir.mkdir(parents=True,exist_ok=False)
    workspace=ROOT/('workspace/iteration2-full-beamer-app'+suffix)
    if workspace.exists():raise RuntimeError('Refuse to overwrite existing benchmark workspace')
    report={'schema_version':1,'status':'RUNNING','workflow':'beamer.from_tex','dataset':'CH03',
        'provider':'mock','real_api':'NOT_RUN','teacher_visual_review':'NOT_RUN',
        'actor':'benchmark_driver','workspace':str(workspace),
        'execution_surface':'Service planning/approval + Worker execution + in-process TestClient HTTP downloads; no TCP server'}
    write(report_dir/'report.json',report)
    before=code_hashes()
    for relative in before:
        destination=report_dir/'source-snapshot'/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/relative,destination)
    report['source_hashes_before_import']=before
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from math_agent.domain import NewRun,ConfirmRequest,ExecuteRequest
    from math_agent.service import Service
    from math_agent.settings import Settings
    from math_agent.worker import Worker
    from math_agent.web.app import create_app
    report['source_hashes_after_import']=code_hashes()
    report['changed_during_import']=[k for k,v in before.items() if report['source_hashes_after_import'].get(k)!=v]
    assert not report['changed_during_import'],'Could not establish exact source snapshot for imported application'
    settings=Settings(workspace=workspace,reference_root=ROOT.parent,llm_provider='mock',
        live_api_enabled=False,llm_streaming=False,api_key=SecretStr(''))
    source=ROOT.parent/'第三章/大学数学（一）(1).tex'
    manuscript=ROOT.parent/'大学数学（一）(1).tex'
    originals={str(p):sha(p.read_bytes()) for name in ('第一章','第二章','第三章')
        for p in sorted((ROOT.parent/name).rglob('*')) if p.is_file()}
    originals[str(manuscript)]=sha(manuscript.read_bytes())
    original_pdf=manuscript.with_suffix('.pdf')
    if original_pdf.exists():originals[str(original_pdf)]=sha(original_pdf.read_bytes())
    report.update(original_sha256=originals,input_tex=str(source),input_tex_sha256=sha(source.read_bytes()),
        manuscript_tex=str(manuscript),manuscript_tex_sha256=sha(manuscript.read_bytes()))
    service=Service(settings,actor='benchmark_driver');worker=Worker(settings);rid=None
    started=time.monotonic()
    try:
        run=service.create(NewRun(workflow_id='beamer.from_tex',topic='第三章完整应用流程验收',
            provider='mock',theme='fduclassroom',trusted_input=True,use_reference_bibliography=True))
        rid=run['id'];report['run_id']=rid
        run=service.attachments(rid,source.name,source.read_bytes())
        report['source_enrichment']=run['input']['source_enrichment']
        write(report_dir/'input_snapshot.json',run)
        original_snapshot=workspace/run['input']['original_source_key']/run['input']['main_file']
        assert original_snapshot.read_bytes()==source.read_bytes()
        assert (workspace/run['input']['original_upload_key']).read_bytes()==source.read_bytes()
        assert run['input']['source_enrichment']['unresolved_keys']==[]
        assert run['input']['source_enrichment']['conflicting_keys']==[]
        service.propose(rid);assert worker.tick()
        run=service.store.get_run(rid);write(report_dir/'plan_snapshot.json',run)
        assert run['status']=='PLAN_READY',run.get('error')
        plan=run['plan'];assert not plan.get('unresolved_blocking_questions')
        assert plan['source_enrichment']==run['input']['source_enrichment']
        report.update(plan_hash=plan['hash'],plan_revision=plan['revision'],section_count=len(plan['sections']),
                      source_unit_count=len(run['input']['units']))
        service.confirm(rid,ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],
            action_id='full-ch03-application-benchmark'))
        service.execute(rid,ExecuteRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],
            idempotency_key='full-ch03-application-benchmark'))
        write(report_dir/'report.json',report)
        print(json.dumps({'stage':'build.started','run_id':rid,'sections':report['section_count'],
            'units':report['source_unit_count'],'bibliography_keys':report['source_enrichment']['added_keys']}),flush=True)
        build_started=time.monotonic();assert worker.tick()
        report['build_elapsed_seconds']=round(time.monotonic()-build_started,3)
        run=service.store.get_run(rid);write(report_dir/'run_snapshot.json',run)
        report.update(run_status=run['status'],run_stage=run['stage'],error=run['error'],request_count=run['request_count'])
        assert run['status']=='AWAITING_USER_REVIEW',run['error']
        assert run['reviews']==[] and run['request_count']==0
        print(json.dumps({'stage':'build.finished','status':run['status'],'artifacts':len(run['artifacts'])}),flush=True)
        downloads=[];named={};download_dir=report_dir/'downloads';download_dir.mkdir()
        with TestClient(create_app(settings),base_url='http://127.0.0.1') as client:
            assert client.get('/api/session').status_code==200
            fetched=client.get('/api/runs/'+rid);assert fetched.status_code==200
            assert fetched.json()['status']=='AWAITING_USER_REVIEW'
            response=client.get('/api/runs/'+rid+'/artifacts');assert response.status_code==200
            api_artifacts=response.json()
            assert {a['artifact_id'] for a in api_artifacts}=={a['artifact_id'] for a in run['artifacts']}
            for item in api_artifacts:
                response=client.get('/api/artifacts/'+item['artifact_id'])
                assert response.status_code==200,(item['name'],response.status_code)
                assert sha(response.content)==item['sha256'],item['name']
                path=download_dir/item['name'];assert not path.exists(),item['name']
                path.write_bytes(response.content)
                downloads.append({'artifact_id':item['artifact_id'],'name':item['name'],'status':response.status_code,
                    'sha256':sha(response.content),'bytes':len(response.content),'media_type':item['media_type'],
                    'physical_page':item.get('metadata',{}).get('physical_page')})
                named[item['name']]=response.content
        quality=json.loads(named['quality_report.json'])
        manifest=json.loads(named['build_manifest.json'])
        inspection=json.loads(named['pdf_inspection.json'])
        assert quality['compile']['status']=='PASS'
        assert quality['fidelity']['status']=='PASS'
        assert not [i for i in quality['issues'] if i.get('severity')=='blocking']
        assert quality['human_visual_review']=='NOT_RUN'
        pages=[x for x in downloads if x['media_type']=='image/png']
        assert len(pages)==inspection['page_count']
        assert sorted(x['physical_page'] for x in pages)==list(range(1,inspection['page_count']+1))
        assert inspection['overlay_map']['status']=='PASS'
        assert manifest['source_bundle_sha256']==sha(named['source_bundle.zip'])
        assert manifest['pdf_sha256']==sha(named['slides.pdf'])
        with zipfile.ZipFile(io.BytesIO(named['source_bundle.zip'])) as archive:
            assert archive.testzip() is None
            members=archive.namelist()
            assert 'slides.tex' in members and 'README.md' in members
            assert 'beamerthemefduclassroom.sty' in members
            for member in manifest['files']:
                assert sha(archive.read(member['path']))==member['sha256']
            assert not any(n.lower().endswith(('.log','.aux','.db','.env')) for n in members)
            zip_members=[{'name':n,'bytes':len(archive.read(n)),'sha256':sha(archive.read(n))} for n in members]
        with service.store.connect() as c:
            events=[{**dict(row),'payload':json.loads(row['payload_json'])} for row in c.execute('SELECT * FROM events WHERE run_id=? ORDER BY sequence',(rid,))]
            checkpoints=[{**dict(row),'output':json.loads(row['output_json'])} for row in c.execute('SELECT * FROM steps WHERE run_id=?',(rid,))]
        write(report_dir/'events.json',events);write(report_dir/'checkpoints.json',checkpoints)
        assert any(x['type']=='plan.confirmed' and x['payload'].get('actor')=='benchmark_driver' for x in events)
        assert not any(x['type']=='human.review' for x in events)
        assert not any(x['type']=='provider.result' for x in events)
        report.update(status='PASS',compile_status=quality['compile']['status'],fidelity_status=quality['fidelity']['status'],
            layout_status=quality['layout']['status'],quality_statuses={k:quality[k]['status'] for k in ('content','math','fidelity','compile','layout','policy','security')},
            physical_pages=inspection['page_count'],rendered_pages=len(inspection['pages']),downloaded_png_count=len(pages),
            overlay_map_status=inspection['overlay_map']['status'],logical_frames=len(inspection['overlay_map']['frames']),
            download_artifacts=downloads,source_zip_members=zip_members,section_checkpoints=len(checkpoints),
            source_provenance_in_approved_plan=True,source_bundle_manifest_verified=True,
            pdf_sha256=sha(named['slides.pdf']),source_bundle_sha256=sha(named['source_bundle.zip']))
    except Exception as exc:
        report.update(status='FAIL',error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
        if rid:write(report_dir/'run_snapshot.json',service.store.get_run(rid))
        raise
    finally:
        report['elapsed_seconds']=round(time.monotonic()-started,3)
        report['source_hashes_after_run']=code_hashes()
        report['changed_source_files_during_run']=[k for k,v in before.items() if report['source_hashes_after_run'].get(k)!=v]
        report['originals_unchanged']=all(Path(p).is_file() and sha(Path(p).read_bytes())==h for p,h in originals.items())
        write(report_dir/'report.json',report)
        print(json.dumps({k:report.get(k) for k in ('status','run_id','run_status','physical_pages','rendered_pages',
            'downloaded_png_count','compile_status','fidelity_status','layout_status','originals_unchanged','elapsed_seconds')}),flush=True)


if __name__=='__main__':main()
