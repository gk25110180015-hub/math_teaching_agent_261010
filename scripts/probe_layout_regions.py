"""Measure real default/FDU template title/footer/body marker geometry, no API."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/'src'))
from math_agent.beamer import render_beamer
from math_agent.compiler import TexCompiler
from math_agent.pdfcheck import inspect_pdf, measure_layout_probe
from math_agent.references import theme_status


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    target = PROJECT/'workspace'/'layout-probes'/datetime.now().strftime('%Y%m%d-%H%M%S')
    target.mkdir(parents=True)
    body = r'''\noindent BodyTopProbe\hfill BodyRightProbe\par
{\large LargeSizeProbe}\par
{\normalsize NormalSizeProbe}\par
{\small SmallSizeProbe}\par
{\footnotesize FootnoteSizeProbe}\par
'''
    unit = {'id':'U001','kind':'explanation','raw_tex':body,'semantic_relations':{},'content_hash':hashlib.sha256(body.encode()).hexdigest()}
    parsed = {'units':[unit],'sections':[{'id':'S01','title':'FrameTitleProbe','source_unit_ids':['U001']}], 'macros':{'definitions':[]}}
    availability = theme_status(PROJECT.parent)
    profiles, results = {}, []
    for theme in ('default','fduclassroom'):
        folder = target/theme
        folder.mkdir()
        if not availability.get(theme,{}).get('available',True):
            results.append({'theme':theme,'status':'BLOCKED','reason':availability[theme].get('reason')})
            continue
        plan = {'theme':theme,'title':'FooterTitleProbe','sections':parsed['sections'],'omissions':[],'additions':[],
                '_layout':{'font_size':'normalsize','split_long':False}}
        rendered = render_beamer(parsed,plan,folder/'source',PROJECT.parent)
        compiled = TexCompiler().compile(folder/'source',rendered['main_file'],folder/'build',trusted=True)
        report = {'test_kind':'windows_actual_template_geometry_probe','theme':theme,'compile':compiled,
                  'real_api':'NOT_RUN','teacher_visual_review':'NOT_RUN'}
        if compiled['status']=='PASS' and compiled.get('pdf_path'):
            pdf = Path(compiled['pdf_path'])
            measurement = measure_layout_probe(pdf)
            profile = {'theme':theme,'measurement':measurement,
                'template_fingerprints':{p.name:sha(p) for p in (folder/'source').iterdir()
                    if p.name in {'workflow_style.tex','workflow_fonts.tex','beamerthemefduclassroom.sty'}},
                'probe_pdf_sha256':sha(pdf),'probe_pdf':str(pdf),'engine':compiled['engine'],
                'measured_at':datetime.now().isoformat(timespec='seconds')}
            profile['profile_sha256']=hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()
            profiles[theme]=profile
            report['measurement']=measurement
            report['profile']=profile
        (folder/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        results.append({'theme':theme,'status':report.get('measurement',{}).get('status',compiled['status']),
                        'report':str(folder/'result.json')})
    index = PROJECT/'reference_index'/'layout_probe_profiles.json'
    index.parent.mkdir(exist_ok=True)
    index.write_text(json.dumps({'schema_version':1,'status':'measured_probe','profiles':profiles,
        'limitations':['这不是三章模板全量校准；仅支持哈希匹配的当前模板几何风险提示。']},ensure_ascii=False,indent=2),encoding='utf-8')
    for theme in profiles:
        folder=target/theme
        pdf=Path(profiles[theme]['probe_pdf'])
        inspected=inspect_pdf(pdf,folder/'pages',beamer=True)
        (folder/'pdf_inspection.json').write_text(json.dumps(inspected,ensure_ascii=False,indent=2),encoding='utf-8')
        summary={'geometry_status':inspected['status'],'page_count':inspected['page_count'],
            'rendered_physical_pages':len(inspected['pages']),'issues':inspected['issues']}
        report_path=folder/'result.json'
        report=json.loads(report_path.read_text(encoding='utf-8'))
        report['inspection_summary']=summary
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        next(item for item in results if item['theme']==theme).update(summary)
        assert all(page['geometry']['body_region']['calibration_status']=='measured_probe' for page in inspected['pages'])
        assert len(inspected['pages'])==inspected['page_count']
    (PROJECT/'reports'/'layout_probe_results.json').write_text(json.dumps({'profiles':str(index),'results':results,
        'real_api':'NOT_RUN','teacher_visual_review':'NOT_RUN'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':
    main()
