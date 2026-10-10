"""Reuse frozen-source/link verifier; adapt only the CH01 baseline and exact counts."""
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source=root/'reports/iteration4/prepare-ch02-post-feedback-audit.py'
code=source.read_text(encoding='utf-8')
replacements={
    "RID = 'fd6736af6ef14be3839e019e86ca1e5c'":"RID = '05748ab6260c40989a560a98e1e2065a'",
    "pre = json.loads((ROOT / 'reports/iteration4/CH02-pre-feedback-semantic-visual.json').read_bytes())":
    """baseline = json.loads((ROOT / 'reports/iteration2/CH01-final-semantic-comparison.json').read_bytes())
pre = {'approved_plan_hash':'60e76cc0b1271ac1b32a9f48c9ae760665bb7180cbdd52df6f5f5958f25db4ac',
 'sections': [], 'artifact_pdf': {'sha256':'387b65fa187488b44e94bc468cb82a956c256cf224a29e636c343f1e7c945b0b'},
 'semantic_review': {'original_16_item_map': baseline['baseline_checklist']}}
for entry in baseline['sections']:
    original=Path(entry['path']).read_bytes()
    assert sha(original)==entry['file_sha256']
    raw=json.loads(original)
    generated=raw.get('section',raw)
    assert sha(canonical(generated))==entry['canonical_sha256']
    pre['sections'].append({'section_id':entry['section_id'],'generated':generated})""",
    'assert len(relations) == 18 and len(links) == 10':'assert len(relations) == 14 and len(links) == 6',
    "'actual_pdf_links': '10/10 PASS'":"'actual_pdf_links': '6/6 PASS'",
    'FROZEN_CH02_POST_FEEDBACK_AUDIT_EVIDENCE_NOT_AUTOMATIC_ACCEPTANCE':'FROZEN_CH01_POST_FEEDBACK_AUDIT_EVIDENCE_NOT_AUTOMATIC_ACCEPTANCE',
}
for before,after in replacements.items():
    assert code.count(before)==1,before
    code=code.replace(before,after)
exec(compile(code,str(source),'exec'),{'__file__':str(source),'__name__':'__main__'})
