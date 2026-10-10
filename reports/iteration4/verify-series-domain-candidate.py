"""Read saved actual units against a candidate; retain immutable-source evidence."""
from pathlib import Path
import hashlib
import importlib.util
import json

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent / '待合并'
spec = importlib.util.spec_from_file_location('math_agent.series_domain_text', folder / 'series_domain_text.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
saved = root / 'workspace/iteration2-live/b/fd6736af6ef14be3/sS03_4728b49f0563/repair-1.json'
raw = saved.read_bytes()
section = json.loads(raw)['section']
issues = module.series_first_term_review(section['units'])
assert [item['location']['unit_id'] for item in issues] == ['S03.U13'], issues
location = issues[0]['location']
unit = next(item for item in section['units'] if item['id'] == location['unit_id'])
span = unit['tex'][location['start']:location['end']]
assert span == r'\sum_{n=1}^{\infty}\frac{1}{n\ln n}', span
hash_record = json.loads((folder / 'series-domain-source-hashes.json').read_text(encoding='utf-8'))
source = root / 'src/math_agent/mathcheck.py'
production_unchanged = hashlib.sha256(source.read_bytes()).hexdigest() == hash_record['original_sha256']
assert production_unchanged
report = {'status': 'PASS', 'kind': 'offline_candidate_saved_unit_review', 'real_api_requests': 0,
    'windows_compile': 'NOT_RUN', 'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
    'production_source_unchanged': production_unchanged, 'source_sha256': hash_record['original_sha256'],
    'saved_candidate': str(saved), 'saved_candidate_sha256': hashlib.sha256(raw).hexdigest(),
    'saved_candidate_unchanged': raw == saved.read_bytes(), 'issues': issues, 'exact_formula_span': span,
    'limitations': ['仅窄语法扫描/定位，并非独立数学证明；错误辨析词判定仍是保守启发式。']}
destination = root / 'reports/iteration4/series-domain-saved-unit-candidate.json'
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
