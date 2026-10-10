"""Freeze explicit final TeX/PDF bytes and render all pages, without accepting them."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def hash_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--tex', type=Path, required=True)
    parser.add_argument('--expected-pdf-sha256', required=True)
    parser.add_argument('--expected-tex-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--final-artifacts-confirmed', action='store_true', required=True,
                        help='Use only after the coordinator supplies frozen final artifacts; not a teacher approval.')
    parser.add_argument('--pdftoppm', default=shutil.which('pdftoppm'))
    args=parser.parse_args()
    if not args.pdftoppm:
        parser.error('Poppler pdftoppm is unavailable; rendering must remain NOT_RUN.')
    reports=Path(__file__).resolve().parent
    output=args.output.resolve()
    if not output.is_relative_to(reports) or output==reports:
        parser.error('Output must be a new child directory of reports/iteration4.')
    inputs={}
    for key in ('pdf','tex'):
        source=getattr(args,key).resolve()
        raw=source.read_bytes()
        actual=hash_bytes(raw)
        if actual!=getattr(args,'expected_'+key+'_sha256').lower():
            parser.error(f'{key} SHA does not match the coordinator freeze; no output created.')
        inputs[key]={'path':str(source),'sha256':actual,'raw':raw}
    output.mkdir(exist_ok=False)
    manifest={'schema_version':1,'captured_at':datetime.now(timezone.utc).isoformat(),
        'run_id':'a45be503af594ce8aae0bb1e4c30184b',
        'plan_hash':'fbd172c8df0c12fca976e9067b04afe5210016559e210ca8dd0c3e7d37f3f1f7',
        'coordinator_confirmed_final_inputs':True,'render_status':'NOT_RUN',
        'agent_semantic_review':'NOT_RUN','agent_visual_review':'NOT_RUN',
        'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN',
        'new_compile_runs':0,'api_calls':0,'inputs':{}}
    for kind,value in inputs.items():
        local=output/f'lecture.{kind}'
        local.write_bytes(value['raw'])
        assert hash_bytes(local.read_bytes())==value['sha256']
        assert hash_bytes(Path(value['path']).read_bytes())==value['sha256']
        manifest['inputs'][kind]={k:v for k,v in value.items() if k!='raw'}
        manifest['inputs'][kind]['snapshot']=local.name
    dump(output/'freeze-render-manifest.json',manifest)
    try:
        import pdfplumber
        with pdfplumber.open(output/'lecture.pdf') as pdf:
            text_pages=[{'physical_page':index+1,'width_pt':page.width,'height_pt':page.height,
                         'text':page.extract_text() or ''} for index,page in enumerate(pdf.pages)]
        dump(output/'pdf-text-pages.json',text_pages)
        tex_lines=inputs['tex']['raw'].decode('utf-8-sig').splitlines()
        units=[]
        for n,line in enumerate(tex_lines,1):
            match=re.fullmatch(r'% UNIT (\S+)\s*',line)
            if match:
                if units:units[-1]['end_line']=n-1
                units.append({'unit_id':match.group(1),'start_line':n,'end_line':len(tex_lines),
                              'pdf_physical_pages':[],'mapping_status':'NOT_ASSESSED'})
        dump(output/'tex-unit-map.json',units)
        pages=output/'pages';pages.mkdir()
        command=[args.pdftoppm,'-png','-r','140',str(output/'lecture.pdf'),str(pages/'page')]
        manifest['render_command']=command
        dump(output/'freeze-render-manifest.json',manifest)
        with (output/'pdftoppm.stdout.log').open('wb') as stdout, (output/'pdftoppm.stderr.log').open('wb') as stderr:
            result=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=600,check=False)
        if result.returncode:
            raise RuntimeError(f'pdftoppm exited {result.returncode}; logs and frozen inputs retained.')
        rendered=sorted(pages.glob('page-*.png'),key=lambda path:int(path.stem.split('-')[-1]))
        assert len(rendered)==len(text_pages), 'Not every physical page was rendered.'
        page_ledger=[{'physical_page':int(path.stem.split('-')[-1]),
                     'image_path':path.relative_to(output).as_posix(),'image_sha256':hash_bytes(path.read_bytes()),
                     'agent_visual_status':'NOT_ASSESSED','observations':[],
                     'teacher_visual_status':'NOT_RUN'} for path in rendered]
        assert [p['physical_page'] for p in page_ledger]==list(range(1,len(text_pages)+1))
        dump(output/'page-review-ledger.json',page_ledger)
        manifest.update(render_status='RENDERED_ALL_PAGES_NOT_VISUALLY_REVIEWED',physical_page_count=len(text_pages))
        for kind,value in inputs.items():
            assert hash_bytes(Path(value['path']).read_bytes())==value['sha256'], 'An original artifact changed during capture.'
    except BaseException as exc:
        manifest.update(render_status='FAILED',error=f'{type(exc).__name__}: {exc}')
        dump(output/'freeze-render-manifest.json',manifest)
        raise
    dump(output/'freeze-render-manifest.json',manifest)
    print(json.dumps({'output':str(output),'physical_pages':manifest['physical_page_count'],
                      'render_status':manifest['render_status'],'agent_visual_review':'NOT_RUN',
                      'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'},ensure_ascii=False))


if __name__=='__main__':main()
