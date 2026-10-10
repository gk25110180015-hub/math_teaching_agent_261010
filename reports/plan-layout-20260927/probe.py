"""Real fourth-chapter input; actual Windows compiler, no model requests or approvals."""
import argparse
import json
from pathlib import Path

from math_agent.beamer_layout import build_measured_beamer
from math_agent.beamer_scope import refresh_beamer_scope
from math_agent.compiler import TexCompiler
from math_agent.util import write_json, now

root=Path(__file__).resolve().parents[2]
folder=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('name');args=parser.parse_args()
output=root/'workspace/q0927'/args.name
output.mkdir(parents=True,exist_ok=False)
data=json.loads((folder/'before/input.json').read_text(encoding='utf-8'))
plan=json.loads((folder/'before/plan.json').read_text(encoding='utf-8'))
original=json.dumps(data,ensure_ascii=False,sort_keys=True)
refresh_beamer_scope(plan,data['parsed'])
write_json(output/'effective-plan.json',plan)
report={'started_at':now(),'model_api':'NOT_RUN','teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'}
try:
    compiler=TexCompiler()
    source,rendered,fidelity,compiled,inspection=build_measured_beamer(data['parsed'],plan,output,root.parent,
        lambda s,e,b:compiler.compile(s,e,b,trusted=True),lambda *args:print(*args,flush=True))
    report.update(source=str(source),compile=compiled,fidelity=fidelity,
                  page_count=(inspection or {}).get('page_count'),layout_status=(inspection or {}).get('status'),
                  logical_frames=len(rendered['frame_plan']),content_frames=sum(f['kind']=='content' for f in rendered['frame_plan']),
                  empty_sections=plan['empty_sections'],original_input_unchanged=original==json.dumps(data,ensure_ascii=False,sort_keys=True))
    write_json(output/'render.json',rendered);write_json(output/'inspection.json',inspection)
    assert compiled['status']=='PASS',compiled['issues']
    assert fidelity['status']=='PASS',fidelity['issues']
    assert inspection and inspection['status']!='FAIL',inspection and inspection['issues']
    assert report['original_input_unchanged']
    assert not any(uid in rendered['source_map'] for uid in ('U0001','U0002'))
    assert not any(f['section_id']=='S02' for f in rendered['frame_plan'])
    report['status']='PASS'
except Exception as exc:
    report.update(status='FAIL',error=str(exc));raise
finally:
    report['finished_at']=now();write_json(output/'result.json',report)
    print(json.dumps({k:report.get(k) for k in ('status','page_count','logical_frames','content_frames','source','error')},ensure_ascii=False),flush=True)
