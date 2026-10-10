"""Freeze final CH02 comparison evidence; never auto-claim visual/teacher review.

Run only after root supplies the completed artifact identity and SHA, after the
existing render-frozen-lecture-audit.py has rendered that exact artifact.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import pdfplumber
from pdfminer.pdftypes import resolve1

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / 'workspace/iteration2-live'
RID = 'fd6736af6ef14be3839e019e86ca1e5c'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--artifact-id', required=True)
parser.add_argument('--expected-sha256', required=True)
parser.add_argument('--render-manifest', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
assert not args.output.exists(), 'Do not overwrite frozen audit evidence.'
pre = json.loads((ROOT / 'reports/iteration4/CH02-pre-feedback-semantic-visual.json').read_bytes())
render = json.loads(args.render_manifest.read_bytes())
assert render['artifact']['artifact_id'] == args.artifact_id
assert render['pdf_sha256'] == args.expected_sha256
c = sqlite3.connect((WS / 'agent.db').resolve().as_uri() + '?mode=ro', uri=True)
c.row_factory = sqlite3.Row
c.execute('PRAGMA query_only=ON')
c.execute('BEGIN')
run = dict(c.execute('SELECT id,status,stage,request_count,active_plan_revision,updated_at FROM runs WHERE id=?', (RID,)).fetchone())
artifact = dict(c.execute('SELECT rowid,* FROM artifacts WHERE run_id=? AND artifact_id=?', (RID, args.artifact_id)).fetchone())
approval = dict(c.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?', (RID, run['active_plan_revision'])).fetchone())
rows = [dict(c.execute('SELECT rowid,* FROM steps WHERE run_id=? AND step_key=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (RID, 'section.S0' + str(i))).fetchone()) for i in range(1, 6)]
c.rollback()
c.close()
assert run['status'] == 'AWAITING_USER_REVIEW'
assert artifact['status'] != 'superseded' and artifact['revision'] == run['active_plan_revision'] == 2
assert approval['hash'] == pre['approved_plan_hash']
pdf_path = WS / artifact['storage_key']
assert sha(pdf_path.read_bytes()) == args.expected_sha256 == artifact['sha256']
version = pdf_path.parent.parent
source = version / 'source/lecture.tex'
source_raw = source.read_bytes()
tex = source_raw.decode('utf-8')
build = json.loads((version / 'build_manifest.json').read_bytes())
assert build['pdf_sha256'] == args.expected_sha256
assert next(f['sha256'] for f in build['files'] if f['path'] == 'lecture.tex') == sha(source_raw)
unit_lines = {m[1]: tex.count('\n', 0, m.start()) + 1 for m in re.finditer(r'^% UNIT (\S+)', tex, re.M)}
old_sections = {s['section_id']: s for s in pre['sections']}
sections = []
for row in rows:
    value = json.loads(row.pop('output_json'))
    assert sha(canonical(value)) == row['output_hash']
    sid = row['step_key'].split('.')[1]
    generated = value['generated']
    old = old_sections[sid]['generated']
    old_units = {u['id']: u for u in old['units']}
    new_units = {u['id']: u for u in generated['units']}
    assert [u['id'] for u in old['units']] == [u['id'] for u in generated['units']]
    for unit in generated['units']:
        assert unit['tex'] in tex, 'Checkpoint body absent from compiled source: ' + unit['id']
    state_path = WS / 'runs' / RID / 'local-repair' / (sid + '.json')
    state_raw = state_path.read_bytes()
    state = json.loads(state_raw)
    candidate_path = WS / state['candidate_key']
    candidate_raw = candidate_path.read_bytes()
    assert sha(candidate_raw) == state['candidate_hash'] and json.loads(candidate_raw) == generated
    assert state['phase'] == 'CHECKED'
    assert sha((WS / value['source_key']).read_bytes()) == value['source_hash']
    changes = [{'unit_id': uid, 'before': old_units[uid], 'after': new_units[uid],
        'before_sha256': sha(canonical(old_units[uid])), 'after_sha256': sha(canonical(new_units[uid])),
        'source_line': unit_lines[uid], 'independent_semantic_review': 'PENDING'}
        for uid in old_units if old_units[uid] != new_units[uid]]
    sections.append({'section_id': sid, 'checkpoint': row, 'generated': generated,
        'generated_sha256': sha(canonical(generated)), 'report': value['report'], 'changed_units': changes,
        'local_recovery': {'path': str(state_path), 'sha256': sha(state_raw), 'phase': state['phase'],
            'candidate_path': str(candidate_path), 'candidate_sha256': sha(candidate_raw),
            'candidate_matches_checkpoint': True}})
aux = pdf_path.with_suffix('.aux').read_text(encoding='utf-8')
links = []
relations = []
with pdfplumber.open(pdf_path) as pdf:
    assert len(pdf.pages) == len(render['pages'])
    page_ids = {p.page_obj.pageid: p.page_number for p in pdf.pages}
    for section in sections:
        sid = section['section_id']
        units = section['generated']['units']
        for question in units:
            if question['kind'] not in ('exercise', 'example'):
                continue
            answers = [u for u in units if u['kind'] == 'solution' and u.get('relates_to') == question['id']]
            assert len(answers) == 1
            relations.append({'question_id': question['id'], 'kind': question['kind'], 'solution_id': answers[0]['id']})
            if question['kind'] != 'exercise':
                continue
            label = 'mathagent:exercise:' + sha(canonical([sid, question['id']]))
            line = next(line for line in aux.splitlines() if line.startswith(r'\newlabel{' + label + '}'))
            groups = re.search(r'\{\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}', line)
            assert groups
            number, aux_page, _, anchor = groups.groups()
            dest = resolve1(pdf.doc.get_dest(anchor.encode('ascii')))
            if isinstance(dest, dict):
                dest = resolve1(dest['D'])
            target_page = page_ids[dest[0].objid]
            assert target_page == int(aux_page)
            occurrences = [{'answer_page': p.page_number, 'rect': [float(v) for v in a['data']['Rect']]}
                for p in pdf.pages for a in p.annots
                if resolve1(a['data'].get('A', {})).get('D') == anchor.encode('ascii')]
            assert len(occurrences) == 1
            links.append({'question_id': question['id'], 'solution_id': answers[0]['id'], 'display_number': number,
                'anchor': anchor, 'question_page': target_page, **occurrences[0],
                'actual_pdf_destination_matches_exercise': True})
assert len(relations) == 18 and len(links) == 10
for page in render['pages']:
    assert sha(Path(page['png_path']).read_bytes()) == page['png_sha256']
    assert sha(Path(page['text_path']).read_bytes()) == page['text_sha256']
result = {'created_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'FROZEN_CH02_POST_FEEDBACK_AUDIT_EVIDENCE_NOT_AUTOMATIC_ACCEPTANCE',
    'run': run, 'artifact': artifact, 'approval': approval,
    'pdf': {'path': str(pdf_path), 'sha256': args.expected_sha256, 'page_count': len(render['pages'])},
    'source': {'path': str(source), 'sha256': sha(source_raw), 'unit_lines': unit_lines},
    'pre_feedback_pdf_sha256': pre['artifact_pdf']['sha256'], 'sections': sections,
    'original_16_criteria': pre['semantic_review']['original_16_item_map'],
    'answer_relations': relations, 'pdf_links': links,
    'visual_pages': [{**page, 'agent_visual_review': 'PENDING_POST_FEEDBACK_FULL_PAGE_VIEW'} for page in render['pages']],
    'quality_report': json.loads((version / 'quality_report.json').read_bytes()),
    'build_manifest': build, 'verification': {'actual_pdf_links': '10/10 PASS',
        'new_api_calls': 0, 'mock_tests': 'NOT_RUN', 'new_windows_compile': 'NOT_RUN',
        'agent_semantic_review': 'PENDING', 'agent_visual_review': 'PENDING',
        'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN'}}
assert sha(pdf_path.read_bytes()) == args.expected_sha256 and source.read_bytes() == source_raw
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'saved': str(args.output), 'pages': len(render['pages']), 'links': len(links),
    'changes': {s['section_id']: [u['unit_id'] for u in s['changed_units']] for s in sections},
    'agent_review': 'PENDING', 'teacher_review': 'NOT_RUN'}, ensure_ascii=False, indent=2))
