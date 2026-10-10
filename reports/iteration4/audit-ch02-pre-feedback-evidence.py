"""Read-only, zero-API evidence for the frozen CH02 pre-feedback artifact."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import pdfplumber
import sympy as sp
from pdfminer.pdftypes import resolve1

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / 'workspace/iteration2-live'
REPORTS = ROOT / 'reports/iteration4'
RID = 'fd6736af6ef14be3839e019e86ca1e5c'
AID = '12e006216ce3467ba012627c3e433721'
EXPECTED = '694d3b6783a984a65164ff3217fd19037c0333a25dac8603e70850b201115382'
DEST = REPORTS / 'CH02-pre-feedback-semantic-visual.json'
assert not DEST.exists(), 'Preserve this frozen audit; choose a new filename.'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


prior = json.loads((REPORTS / 'CH02-intermediate-semantic.json').read_bytes())
render = json.loads((REPORTS / 'CH02-pre-feedback-pages-61/render-manifest.json').read_bytes())
conn = sqlite3.connect((WS / 'agent.db').resolve().as_uri() + '?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA query_only=ON')
conn.execute('BEGIN')
run = dict(conn.execute('SELECT id,status,stage,active_plan_revision,request_count,updated_at FROM runs WHERE id=?', (RID,)).fetchone())
artifact = dict(conn.execute('SELECT rowid,* FROM artifacts WHERE run_id=? AND artifact_id=?', (RID, AID)).fetchone())
rows = [dict(conn.execute('SELECT rowid,* FROM steps WHERE run_id=? AND step_key=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (RID, 'section.S0' + str(i))).fetchone()) for i in range(1, 6)]
approval = dict(conn.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?', (RID, run['active_plan_revision'])).fetchone())
conn.rollback()
conn.close()
assert run['status'] == 'AWAITING_USER_REVIEW' and run['request_count'] == 61
assert artifact['status'] != 'superseded' and artifact['revision'] == 2
assert approval == prior['approval']
pdf_path = WS / artifact['storage_key']
assert sha(pdf_path.read_bytes()) == EXPECTED == artifact['sha256'] == render['pdf_sha256']
version = pdf_path.parent.parent
source = version / 'source/lecture.tex'
raw = source.read_bytes()
tex = raw.decode('utf-8')
assert sha(raw) == prior['combined_source']['sha256']
unit_lines = {m[1]: tex.count('\n', 0, m.start()) + 1 for m in re.finditer(r'^% UNIT (\S+)', tex, re.M)}
sections = []
for row, old in zip(rows, prior['sections']):
    output_raw = row.pop('output_json')
    payload = json.loads(output_raw)
    assert sha(canonical(payload)) == row['output_hash']
    assert payload['generated'] == old['generated']
    assert sha((WS / payload['source_key']).read_bytes()) == payload['source_hash']
    sections.append({'section_id': old['section_id'], 'checkpoint': row,
        'generated_canonical_sha256': sha(canonical(payload['generated'])),
        'identical_to_intermediate_snapshot': True,
        'unit_sha256': old['unit_evidence'], 'generated': payload['generated']})
units = {u['id']: u for s in sections for u in s['generated']['units']}
assert len(units) == 82
aux = pdf_path.with_suffix('.aux').read_text(encoding='utf-8')
links = []
with pdfplumber.open(pdf_path) as pdf:
    assert len(pdf.pages) == 17
    by_pageid = {p.page_obj.pageid: p.page_number for p in pdf.pages}
    for section in sections:
        sid = section['section_id']
        for question in section['generated']['units']:
            if question['kind'] != 'exercise':
                continue
            solutions = [u for u in section['generated']['units'] if u['kind'] == 'solution' and u.get('relates_to') == question['id']]
            assert len(solutions) == 1
            label = 'mathagent:exercise:' + sha(canonical([sid, question['id']]))
            line = next(x for x in aux.splitlines() if x.startswith(r'\newlabel{' + label + '}'))
            groups = re.search(r'\{\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}', line)
            assert groups, line
            number, aux_page, _, anchor = groups.groups()
            dest = resolve1(pdf.doc.get_dest(anchor.encode('ascii')))
            if isinstance(dest, dict):
                dest = resolve1(dest['D'])
            target_page = by_pageid[dest[0].objid]
            assert target_page == int(aux_page)
            occurrences = [{'answer_page': p.page_number, 'rect': [float(v) for v in a['data']['Rect']]}
                for p in pdf.pages for a in p.annots
                if resolve1(a['data'].get('A', {})).get('D') == anchor.encode('ascii')]
            assert len(occurrences) == 1
            links.append({'question_id': question['id'], 'solution_id': solutions[0]['id'],
                'display_number': number, 'anchor': anchor, 'question_page': target_page,
                **occurrences[0], 'actual_pdf_destination_matches_exercise': True})
assert len(links) == 10
n = sp.Symbol('n', positive=True, integer=True)
calculations = []
for unit_id, part, a, b, expected in [
    ('S03.U14', 1, (3*n+1)/(n**3+2), 1/n**2, 3),
    ('S03.U14', 2, 1/(n**2+1), 1/n**2, 1),
    ('S03.U16', 2, (n+1)/(n**2+3), 1/n, 1),
    ('S03.U16', 3, 1/sp.sqrt(n**2+n), 1/n, 1),
]:
    value = sp.limit(a/b, n, sp.oo)
    assert value == expected
    calculations.append({'unit_id': unit_id, 'part': part, 'a_n': str(a), 'b_n': str(b),
        'ratio': str(sp.factor(a/b)), 'limit': str(value), 'expected': str(expected),
        'engine': 'SymPy ' + sp.__version__, 'status': 'PASS_FOR_THIS_EXPRESSION_ONLY'})

observations = {
    1: '标题、部分和与定义可读；标题区域留白正常。',
    2: '第一节末尾与第二节起始正常；页眉使用本页后出现的节名，非错误引用。',
    3: '必要条件、调和级数分块证明及线性性质可读，公式无裁切。',
    4: '余项与例题2.7跨页接续正常；未见孤立编号或遮挡。',
    5: '第二节练习后转入第三节；正项部分和有界定理证明正常跨页。',
    6: '比较与极限比较定理条件、分式及不等式清晰；证明跨页不丢字。',
    7: '几何级数显式限制正首项/非负公比；p级数分情形及积分判别条件可见。',
    8: '积分判别证明与例题3.8题面清楚；对数级数下限n=2可见。',
    9: '例题3.8直接比较/积分解正确；练习3.9三式可读；转入交错级数。',
    10: '交错证明和余项声明可读，具体数值样本未代替一般证明。',
    11: '偶数部分和差明确m>=2，避免S0；余项界及练习4.5可读。',
    12: '练习4.6后余项证明有重复但无错误；绝对收敛证明跨页正常。',
    13: '绝对收敛推出收敛、分类定理及综合例题正常排版；细分分式可辨。',
    14: '分类解答、方法选择说明及练习5.8-5.10可读；练习5.10正常跨页。',
    15: 'S05.U18导航文字与紧随的全章答案顺序冲突；首个答案是练习1.6。排版本身无裁切。',
    16: '练习2.10、3.9、4.5及4.6答案正常；3.9仍为直接比较，无极限比较替代解。',
    17: '练习5.8-5.10全部答案可读，余项阈值说明正确；密集但未见重叠、截断或页面溢出。',
}
pages = []
for item in render['pages']:
    assert sha(Path(item['png_path']).read_bytes()) == item['png_sha256']
    assert sha(Path(item['text_path']).read_bytes()) == item['text_sha256']
    pages.append({**item, 'agent_visual_review': 'VIEWED_FULL_PAGE_IMAGE',
        'agent_observation': observations[item['physical_page']],
        'layout_blocker_observed': False, 'teacher_visual_review': 'NOT_RUN'})
quality = json.loads((version / 'quality_report.json').read_bytes())
inspection = json.loads((version / 'pdf_inspection.json').read_bytes())
summary = {k: v.get('status') for k, v in quality.items() if isinstance(v, dict)}
criteria = []
for c in prior['original_16_item_intermediate_map']:
    criteria.append({'id': c['id'], 'title': c['title'], 'original_scope': c['original_scope'],
        'pre_feedback_assessment': c['intermediate_status'], 'note': c['note'],
        'evidence': c['evidence'], 'teacher_verdict': 'NOT_RUN'})
assert len(criteria) == 16
result = {'created_at': datetime.now(timezone.utc).isoformat(), 'scope': 'CH02_PRE_FEEDBACK_COMPLETE_ARTIFACT_AGENT_AUDIT',
    'run_snapshot': run, 'artifact': artifact, 'approved_plan_hash': approval['hash'],
    'artifact_pdf': {'path': str(pdf_path), 'sha256': EXPECTED, 'pages': 17},
    'render_manifest': str(REPORTS / 'CH02-pre-feedback-pages-61/render-manifest.json'),
    'source': {'path': str(source), 'sha256': sha(raw), 'all_82_units_identical_to_intermediate': True, 'unit_lines': unit_lines},
    'sections': sections, 'semantic_review': {'all_units_reviewed': 82, 'original_criteria_reviewed': 16,
        'original_16_item_map': criteria, 'known_findings': prior['known_findings'],
        'answer_relations': prior['answer_relation_audit'],
        'scope_differences_not_required_plan_defects': prior['source_baseline_scope_differences'],
        'optional_style_only': prior['optional_style_suggestions']},
    'feedback_reverified': [
        {**prior['recheck_feedback'][0], 'pre_feedback_status': 'STILL_ACCURATE', 'pdf_page': 15,
         'actual_first_answer': 'S01.U09 / exercise 1.6 / page 15',
         'own_section_answers': [x for x in links if x['question_id'].startswith('S05.')],
         'S05_U18_clickable_link': False,
         'finding_precision': 'Misleading prose navigation, not a broken existing PDF answer backlink.'},
        {**prior['recheck_feedback'][1], 'pre_feedback_status': 'STILL_ACCURATE', 'pdf_pages': [6, 7, 9, 13, 14, 16, 17],
         'actual_alternative_ratio_checks': calculations,
         'finding_precision': 'Approved learning-goal application gap; existing direct-comparison proofs are mathematically valid.'}],
    'pdf_answer_backlinks': links, 'visual_review': {'agent_pages_viewed': 17, 'total_pages': 17,
        'layout_blocker_observed': False, 'pages': pages, 'teacher_review': 'NOT_RUN'},
    'verification': {'new_model_api_calls': 0, 'mock_tests': 'NOT_RUN_IN_THIS_AUDIT',
        'deterministic_actual_pdf_link_checks': '10/10 PASS', 'symbolic_ratio_checks': calculations,
        'new_windows_compile': 'NOT_RUN', 'preserved_product_quality_statuses': summary,
        'preserved_pdf_inspection_status': inspection.get('status'),
        'teacher_math_acceptance': 'NOT_RUN', 'teacher_visual_acceptance': 'NOT_RUN',
        'agent_did_not_modify_pdf_source_or_production': True},
    'limitations': ['This is the complete pre-feedback artifact, not the future post-feedback final version.',
        'Agent semantic review and image inspection do not constitute teacher acceptance or formal proof.',
        '16 source-reference criteria were all inspected; no 16/16 or automatic correctness percentage is claimed.',
        'No new API invocation or Windows compilation was performed for this report; existing compile evidence is preserved separately.']}
assert sha(pdf_path.read_bytes()) == EXPECTED and sha(source.read_bytes()) == sha(raw)
DEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'saved': str(DEST), 'pdf_sha256': EXPECTED, 'units_identical': len(units),
    'pages_agent_viewed': len(pages), 'answer_backlinks': links, 'symbolic_ratios': calculations,
    'quality_statuses': summary, 'inspection_status': inspection.get('status')}, ensure_ascii=False, indent=2))
