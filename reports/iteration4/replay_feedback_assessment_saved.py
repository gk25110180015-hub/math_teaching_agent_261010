"""Read-only saved real outputs through final candidate; no network/reclassification tuning."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT/'src'))
source = OUT/'feedback_review.candidate.py'
spec = importlib.util.spec_from_file_location('math_agent._feedback_final_replay', source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
folder = OUT/'live-feedback-controls-v2-20260920-1808'
cases = json.loads((folder/'frozen/fixtures-local-only.json').read_bytes())['cases']
rows = []
for case in cases:
    path = folder/case['id']/'response.json'
    response = json.loads(path.read_bytes())
    try:
        receipt, issues = module.validate_assessment(response, case['input'])
        actual = {i['id']: i['status'] for i in receipt['items']}
        rows.append({'case_id': case['id'], 'response_path': path.relative_to(ROOT).as_posix(),
            'response_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'protocol_evidence_validation': 'PASS', 'expected_unchanged': case['expected'], 'actual': actual,
            'strict_expected_match': actual == case['expected'], 'scoped_issues': issues,
            'repair_targets': {i['id']: i['repair_unit_ids'] for i in receipt['items']}})
    except Exception as exc:
        rows.append({'case_id': case['id'], 'protocol_evidence_validation': 'FAIL', 'error': str(exc)})
result = {'mode': 'OFFLINE_REPLAY_OF_SAVED_REAL_API_RESPONSES', 'api_calls_in_this_run': 0,
    'candidate_raw_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'frozen_real_probe_helper_sha256': json.loads((folder/'state.json').read_bytes())['frozen_sha256']['helper.py'],
    'cases': rows, 'teacher_review': 'NOT_RUN',
    'limitations': ['Strict expected mismatch remains unchanged; valid teaching judgment disagreement is not discarded or rerolled.',
        'Replay tests evidence/schema and repair targets, not independent mathematical correctness.']}
(OUT/'feedback-assessment-final-saved-replay.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
