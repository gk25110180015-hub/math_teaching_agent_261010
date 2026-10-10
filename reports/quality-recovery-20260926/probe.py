"""Read-only task replay into a new isolated Windows build directory; no model calls."""
import argparse
import json
from pathlib import Path
import sqlite3

from math_agent.beamer import render_beamer
from math_agent.compiler import TexCompiler
from math_agent.pdfcheck import inspect_pdf
from math_agent.util import write_json

p = argparse.ArgumentParser()
p.add_argument('directory', type=Path)
p.add_argument('--refine', action='store_true')
args = p.parse_args()
assert not args.directory.exists(), 'Keep all previous probe evidence'
rid = 'e53fd34585fb4bc9af2a85fd994d610a'
with sqlite3.connect(Path('workspace/agent.db').resolve().as_uri()+'?mode=ro', uri=True) as c:
    inp, rev = c.execute('select input_json,active_plan_revision from runs where id=?', (rid,)).fetchone()
    row = c.execute('select canonical_json from plans where run_id=? and revision=?', (rid, rev)).fetchone()
data, plan = json.loads(inp), json.loads(row[0])
if args.refine:
    plan['_layout']={'font_size':'footnotesize','split_long':True,'separate_units':True,'segment_capacity':260}
args.directory.mkdir(parents=True)
rendered = render_beamer(data['parsed'], plan, args.directory/'source', Path('..').resolve())
write_json(args.directory/'render.json', rendered)
print('render', rendered['fidelity']['status'], 'adaptations',len(rendered['presentation_adaptations']), flush=True)
result = TexCompiler().compile(args.directory/'source', 'slides.tex', args.directory/'build', trusted=True)
write_json(args.directory/'compile.json', result)
print(json.dumps({'compile':result['status'], 'issues':result.get('issues',[])}, ensure_ascii=False), flush=True)
if result.get('pdf_path'):
    pdf=Path(result['pdf_path'])
    (pdf.parent/'frame_ids.txt').write_text('\n'.join(f['frame_id'] for f in rendered['frame_plan']), encoding='utf-8')
    inspection=inspect_pdf(pdf,args.directory/'pages',beamer=True)
    write_json(args.directory/'inspection.json', inspection)
    print('PDF',inspection['status'],'pages',inspection['page_count'],flush=True)
