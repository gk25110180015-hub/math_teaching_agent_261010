"""Render a pinned, current finished lecture artifact for independent page review."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned_artifact(workspace, run_id, artifact_id):
    connection=sqlite3.connect((workspace/'agent.db').as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    connection.execute('PRAGMA query_only=ON');connection.execute('BEGIN')
    try:
        run=dict(connection.execute('SELECT id,status,stage,active_plan_revision,updated_at FROM runs WHERE id=?',(run_id,)).fetchone())
        assert run['status'] in ('AWAITING_USER_REVIEW','COMPLETED','COMPLETED_WITH_WARNINGS'), 'Task has no finished reviewable artifact'
        artifact=dict(connection.execute("SELECT rowid,* FROM artifacts WHERE run_id=? AND revision=? AND name='lecture.pdf' AND status!='superseded' ORDER BY created_at DESC,rowid DESC LIMIT 1",(run_id,run['active_plan_revision'])).fetchone())
        assert artifact['artifact_id']==artifact_id, 'Artifact is not the latest current PDF'
        plan=dict(connection.execute('SELECT revision,hash FROM plans WHERE run_id=? AND revision=?',(run_id,run['active_plan_revision'])).fetchone())
        approval=dict(connection.execute('SELECT revision,hash FROM approvals WHERE run_id=? AND revision=?',(run_id,run['active_plan_revision'])).fetchone())
        assert plan==approval, 'Current plan approval mismatch'
        return run,artifact,plan
    finally:
        connection.rollback();connection.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=ROOT/'workspace/iteration2-live')
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--artifact-id',required=True)
    parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    workspace=args.workspace.resolve();output=args.output_dir.resolve()
    assert output.is_relative_to((ROOT/'reports').resolve()) and output!=(ROOT/'reports').resolve() and not output.exists()
    for key in list(os.environ):
        if key.startswith('MATH_AGENT_'):os.environ.pop(key,None)
    renderer=shutil.which('pdftoppm.exe') or shutil.which('pdftoppm')
    assert renderer, 'Poppler pdftoppm unavailable; no rendering claimed'
    run,artifact,plan=pinned_artifact(workspace,args.run_id,args.artifact_id)
    pdf=(workspace/artifact['storage_key']).resolve()
    assert pdf.is_relative_to(workspace)
    original=pdf.read_bytes()
    assert sha(original)==artifact['sha256']==args.expected_sha256
    output.mkdir(parents=True,exist_ok=False)
    report={'status':'RENDERING','created_at':datetime.now(timezone.utc).isoformat(),
        'run_snapshot':run,'approved_plan':plan,'artifact':artifact,'pdf_path':str(pdf),
        'pdf_sha256':sha(original),'model_requests':0,'new_windows_compile':'NOT_RUN',
        'agent_visual_review':'NOT_RUN','teacher_visual_review':'NOT_RUN','pages':[],
        'renderer':str(renderer),'renderer_sha256':sha(Path(renderer).read_bytes()),'render_dpi':150}
    destination=output/'render-manifest.json'

    def save():destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

    save()
    try:
        import pdfplumber
        from PIL import Image
        from math_agent.compiler import safe_child_env
        env=safe_child_env(Path(renderer),output)
        Path(env['TEMP']).mkdir(parents=True,exist_ok=True)
        report['command']=[renderer,'-r','150','-png',str(pdf),str(output/'page')]
        process=subprocess.run(report['command'],capture_output=True,env=env,timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        (output/'poppler.stdout.log').write_bytes(process.stdout)
        (output/'poppler.stderr.log').write_bytes(process.stderr)
        report['renderer_returncode']=process.returncode
        assert process.returncode==0, 'Poppler failed; logs retained'
        images=sorted(output.glob('page-*.png'),key=lambda p:int(p.stem.rsplit('-',1)[1]))
        with pdfplumber.open(pdf) as document:
            assert len(document.pages)==len(images)>0, 'All-page PNG coverage failed'
            report['page_count']=len(document.pages)
            for number,(page,png) in enumerate(zip(document.pages,images),1):
                text=page.extract_text() or ''
                text_path=output/f'page-{number:04d}.txt'
                text_path.write_text(text,encoding='utf-8')
                with Image.open(png) as image:size=list(image.size)
                report['pages'].append({'physical_page':number,'png_path':str(png),'png_sha256':sha(png.read_bytes()),
                    'pixel_size':size,'text_path':str(text_path),'text_sha256':sha(text_path.read_bytes()),
                    'page_size_pt':[page.width,page.height],
                    'link_annotations':sum(getattr(a['data'].get('Subtype'),'name',None)=='Link' for a in page.annots),
                    'agent_visual_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'})
                save()
        _,after_artifact,after_plan=pinned_artifact(workspace,args.run_id,args.artifact_id)
        assert after_plan==plan and after_artifact['sha256']==artifact['sha256'] and pdf.read_bytes()==original
        report['status']='ALL_PAGES_RENDERED_VISUAL_REVIEW_NOT_RUN'
        report['source_unchanged']=True
    except BaseException as exc:
        report.update(status='FAIL',error_type=type(exc).__name__,error=str(exc))
        raise
    finally:
        report['finished_at']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({'manifest':str(destination),'status':report['status'],'pages':report['page_count']},ensure_ascii=False))


if __name__=='__main__':main()
