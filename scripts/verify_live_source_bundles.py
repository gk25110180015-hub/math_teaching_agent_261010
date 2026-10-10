"""Recompile actual live lecture ZIP deliveries in new directories, with no model calls."""
import argparse
import json
from pathlib import Path
import time
import uuid
import zipfile

import pdfplumber

from math_agent.compiler import TexCompiler
from math_agent.parsing import safe_extract_zip
from math_agent.settings import PROJECT_ROOT, Settings
from math_agent.util import digest, now, scrub, write_json


def pdf_signature(path):
    with pdfplumber.open(path) as document:
        return {'pages': len(document.pages), 'text': [page.extract_text() or '' for page in document.pages],
                'links_per_page': [sum(getattr(a['data'].get('Subtype'), 'name', None) == 'Link'
                                       for a in page.annots) for page in document.pages]}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,default=PROJECT_ROOT/'reports/iteration2/live-lectures')
    parser.add_argument('--output-dir', type=Path,
                        help='New evidence directory under reports; must not exist. Default retains iteration2 report layout.')
    parser.add_argument('--build-dir', type=Path,
                        help='New clean extraction/compile directory under workspace; must not exist.')
    parser.add_argument('--case', action='append', choices=('smoke','CH01','CH02','CH03'),
                        help='Verify selected completed cases; default verifies all four.')
    args=parser.parse_args(argv)
    stamp=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    output=(args.build_dir or PROJECT_ROOT/'workspace/iteration2-live-delivery'/stamp).resolve()
    workspace=(PROJECT_ROOT/'workspace').resolve()
    if output == workspace or not output.is_relative_to(workspace) or output.exists():
        parser.error('--build-dir must be a new child directory of workspace')
    if args.output_dir:
        report_dir=args.output_dir.resolve()
        reports=(PROJECT_ROOT/'reports').resolve()
        if report_dir == reports or not report_dir.is_relative_to(reports) or report_dir.exists():
            parser.error('--output-dir must be a new child directory of reports')
        report_path=report_dir/'report.json'
    else:
        report_path=PROJECT_ROOT/'reports/iteration2'/('live-zip-recompile-'+stamp+'.json')
    if report_path.exists():
        parser.error('Refusing to replace an existing verification report')
    report_path.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir(parents=True,exist_ok=False)
    report={'created_at':now(),'output':str(output),'run_dir':str(args.run_dir.resolve()),
            'report_path':str(report_path),'model_requests':0,'teacher_visual_review':'NOT_RUN','cases':[]}
    write_json(report_path,report)
    for name in dict.fromkeys(args.case or ('smoke','CH01','CH02','CH03')):
        result={'case':name,'status':'NOT_RUN'}
        report['cases'].append(result)
        try:
            comparison_path=args.run_dir/name/'comparison.json'
            comparison_bytes=comparison_path.read_bytes()
            data=json.loads(comparison_bytes)
            result.update(comparison_path=str(comparison_path.resolve()),comparison_sha256=digest(comparison_bytes),
                          run_id=data['run_id'],run_status=data['run_status'])
            if data['run_status'] not in ('AWAITING_USER_REVIEW','COMPLETED','COMPLETED_WITH_WARNINGS'):
                result['reason']='No completed draft available: '+data['run_status']
                continue
            artifacts={a['name']:a for a in data['generated']['artifacts']
                       if a.get('selected_for_current', a.get('status')!='superseded')}
            bundle=artifacts['source_bundle.zip'];pdf=artifacts['lecture.pdf']
            zip_path=Path(bundle['path']);pdf_path=Path(pdf['path'])
            assert digest(zip_path.read_bytes())==bundle['sha256'], 'ZIP hash mismatch'
            assert digest(pdf_path.read_bytes())==pdf['sha256'], 'PDF hash mismatch'
            result.update(zip_sha256=bundle['sha256'],original_pdf_sha256=pdf['sha256'],
                          bundle_artifact_id=bundle.get('artifact_id'),pdf_artifact_id=pdf.get('artifact_id'),
                          original_zip_path=str(zip_path.resolve()),original_pdf_path=str(pdf_path.resolve()))
            folder=output/name;source=folder/'source';source.mkdir(parents=True,exist_ok=False)
            comparison_snapshot=folder/'comparison-snapshot.json'
            comparison_snapshot.write_bytes(comparison_bytes)
            result['comparison_snapshot']=str(comparison_snapshot)
            with zipfile.ZipFile(zip_path) as archive:
                assert archive.testzip() is None,'ZIP CRC failure'
            members=safe_extract_zip(zip_path.read_bytes(),source)
            source_hashes={p.relative_to(source).as_posix():digest(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
            compiler=TexCompiler(Settings().xelatex_path)
            compiled=compiler.compile(source,'lecture.tex',folder/'build',trusted=True)
            write_json(folder/'compile.json',compiled)
            result.update(run_id=data['run_id'],zip_sha256=bundle['sha256'],source_hashes=source_hashes,
                          members=members,compile_status=compiled['status'],compile_report=str(folder/'compile.json'))
            if compiled['status']!='PASS':
                result['status']='FAIL'
                continue
            original=pdf_signature(pdf_path)
            rebuilt=pdf_signature(folder/'build/lecture.pdf')
            unchanged=source_hashes=={p.relative_to(source).as_posix():digest(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
            result.update(page_count=rebuilt['pages'],all_page_text_equal=original['text']==rebuilt['text'],
                          link_counts_equal=original['links_per_page']==rebuilt['links_per_page'],source_unchanged=unchanged,
                          original_links_per_page=original['links_per_page'],rebuilt_links_per_page=rebuilt['links_per_page'],
                          original_page_text_hashes=[digest(t) for t in original['text']],
                          rebuilt_page_text_hashes=[digest(t) for t in rebuilt['text']],
                          pdf_path=str(folder/'build/lecture.pdf'),rendered_again=False)
            result['status']='PASS' if original==rebuilt and unchanged else 'FAIL'
        except Exception as error:
            result.update(status='FAIL',error_type=type(error).__name__,error=scrub(str(error)))
        finally:
            write_json(report_path,report)
    report['status']='PASS' if all(c['status']=='PASS' for c in report['cases']) else 'NEEDS_REVIEW'
    report['limitations']=['Native Windows compilation, not isolated execution.',
                           'Rebuilt page text and link counts are compared; rebuilt pages are not rendered again or teacher-reviewed.']
    write_json(report_path,report)
    print(json.dumps({'status':report['status'],'report':str(report_path),'cases':report['cases']},ensure_ascii=True))
    return 0 if report['status']=='PASS' else 2


if __name__=='__main__':
    raise SystemExit(main())
