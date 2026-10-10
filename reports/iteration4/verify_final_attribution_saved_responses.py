"""Revalidate already completed real responses with final helper, without API."""
import hashlib
import importlib.util
import json
from pathlib import Path

OUT = Path(__file__).parent
live = OUT / 'live-attribution-controls-20260920-1726'
helper_path = OUT / 'review-evidence-attribution.candidate.py'
spec = importlib.util.spec_from_file_location('final_attribution_helper', helper_path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
fixtures = json.loads((live / 'frozen/fixtures-local-only.json').read_bytes())['cases']
results = []
for case in fixtures:
    folder = live / case['case_id']
    request = json.loads((folder / 'input.json').read_bytes())
    response = json.loads((folder / 'response.json').read_bytes())
    context = request['review_context']
    conflicts = helper.detect_attribution_conflicts(request['original_review'], context['units'], context['prior_sections'])
    assert conflicts == request['conflicts']
    catalog = helper.unit_catalog(context['units'], context['prior_sections'])
    effective, validated = helper.validate_adjudication(request['original_review'], conflicts, response, catalog)
    expected = case['expected']
    disposition = validated['decisions'][0]['disposition']
    allowed = expected.get('allowed_dispositions', [expected.get('disposition')])
    assert disposition in allowed
    target = conflicts[0]['target_unit_id']
    blocking = any(issue['unit_id'] == target and issue['severity'] in ('blocking', 'review') for issue in effective['issues'])
    assert blocking == expected['remaining_target_blocking']
    unaffected = [issue for n, issue in enumerate(request['original_review']['issues']) if n not in {c['issue_index'] for c in conflicts}]
    assert all(issue in effective['issues'] for issue in unaffected)
    results.append({'case_id': case['case_id'], 'classification': 'PASS', 'disposition': disposition,
        'remaining_target_blocking': blocking, 'other_original_issues_preserved': True,
        'input_raw_sha256': hashlib.sha256((folder / 'input.json').read_bytes()).hexdigest(),
        'response_raw_sha256': hashlib.sha256((folder / 'response.json').read_bytes()).hexdigest()})
report = {'status': 'PASS', 'api_calls': 0, 'kind': 'OFFLINE_VALIDATION_OF_TWO_SAVED_REAL_RESPONSES',
    'final_helper_raw_sha256': hashlib.sha256(helper_path.read_bytes()).hexdigest(),
    'real_api_control_directory': str(live), 'results': results,
    'limitation': 'No repeated API adjudication; final recovery/error-code changes are covered by separate mock tests. Two known controls are targeted regression, not blind accuracy or model weight training.'}
target = OUT / 'review-attribution-final-helper-saved-replay.json'
target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
