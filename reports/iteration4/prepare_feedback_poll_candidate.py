"""Prepare an isolated browser regression for run/event refresh decoupling."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
folder = REPORTS / 'feedback-poll-candidate'
folder.mkdir(exist_ok=False)
source = ROOT / 'src/math_agent/web/static/app.js'
test = ROOT / 'tests/e2e/test_feedback_receipts.py'
original = source.read_bytes()
text = original.decode('utf-8')
old = '''  const events = await api(`/api/runs/${id}/events?after=${state.events.at(-1)?.sequence || 0}`);
  if (id !== state.selected || epoch !== state.epoch) return;
  state.run = run;
  state.events.push(...(Array.isArray(events) ? events : events.events || []));
'''
assert text.count(old) == 1
text = text.replace(old, '  state.run = run;\n', 1)
old = '''  if (force || fingerprint !== state.fingerprint) { state.fingerprint = fingerprint; renderRun(run); }
  renderEvents();
'''
new = '''  if (force || fingerprint !== state.fingerprint) { state.fingerprint = fingerprint; renderRun(run); }
  const events = await api(`/api/runs/${id}/events?after=${state.events.at(-1)?.sequence || 0}`);
  if (id !== state.selected || epoch !== state.epoch) return;
  state.events.push(...(Array.isArray(events) ? events : events.events || []));
  renderEvents();
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)
(folder/'app.before.js').write_bytes(original)
(folder/'app.candidate.js').write_bytes(text.encode('utf-8'))
original_test = test.read_bytes()
candidate = original_test.decode('utf-8').replace('import json\n', '''import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/e2e'))
''', 1)
candidate = candidate.replace('    posts = []\n', '''    candidate_js = os.environ.get('MATH_AGENT_E2E_APP_JS_CANDIDATE')
    if candidate_js:
        candidate_path = Path(candidate_js).resolve()
        assert candidate_path.is_relative_to((ROOT/'reports/iteration4').resolve())
        page.route('**/static/app.js', lambda route: route.fulfill(status=200,
            content_type='application/javascript', body=candidate_path.read_text(encoding='utf-8')))
        page.reload()
    posts = []
''', 1)
start = candidate.index('    # Change only the receipt in one browser GET response.')
end = candidate.index("    page.screenshot(path=str(evidence/'receipt-visible-with-draft.png')", start)
candidate = candidate[:start] + '''    # A current run snapshot must render even while its separate event log GET
    # remains pending. Keep the new snapshot stable until both UI assertions pass.
    updated = json.loads(json.dumps(after))
    updated['feedback_review']['items'][0]['reason'] = '离线展示测试：新回执到达，任务的阶段和产物没有变化。'
    run_pattern = '**' + run_url
    events_pattern = re.compile(re.escape(local_services[0] + run_url + '/events') + r'\\?after=\\d+$')
    receipt_hits, held_events = [], []

    def updated_receipt(route):
        receipt_hits.append(route.request.url)
        route.fulfill(status=200, content_type='application/json', body=json.dumps(updated, ensure_ascii=False))

    def hold_events(route):
        held_events.append(route)

    page.route(run_pattern, updated_receipt)
    page.route(events_pattern, hold_events)
    try:
        with page.expect_request(lambda request: bool(events_pattern.fullmatch(request.url)), timeout=10000):
            expect(page.locator('[data-feedback-id="F1"]')).to_contain_text('新回执到达', timeout=10000)
        expect(page.locator('#recheck-feedback')).to_have_value(draft)
        assert receipt_hits, 'The normal timer must actually request the changed run snapshot'
        assert held_events, 'The event log request must be held while the new receipt is visible'
    finally:
        save(evidence/'receipt-polling-evidence.json', {
            'snapshot_get_hits': len(receipt_hits), 'held_event_requests': len(held_events),
            'event_requests_released_at_observation': False,
            'browser_state': page.evaluate("() => ({polling:state.polling,busy:state.busy,editing:state.editing,hidden:document.hidden,reason:state.run?.feedback_review?.items?.[0]?.reason})"),
            'candidate_js': candidate_js, 'manual_refresh_after_route_installation': False,
            'real_api': 'NOT_RUN', 'teacher_review': 'NOT_RUN'})
        for route in held_events:
            route.continue_()
        page.unroute(events_pattern, hold_events)
        page.unroute(run_pattern, updated_receipt)
''' + candidate[end:]
(folder/'test_feedback_receipts.before.py').write_bytes(original_test)
(folder/'test_feedback_receipts_candidate.py').write_text(candidate, encoding='utf-8')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest = {'status':'CANDIDATE_NOT_DEPLOYED', 'files':[
    {'source':'src/math_agent/web/static/app.js','candidate':'feedback-poll-candidate/app.candidate.js',
     'baseline_sha256':sha(source),'candidate_sha256':sha(folder/'app.candidate.js')},
    {'source':'tests/e2e/test_feedback_receipts.py','candidate':'feedback-poll-candidate/test_feedback_receipts_candidate.py',
     'baseline_sha256':sha(test),'candidate_sha256':sha(folder/'test_feedback_receipts_candidate.py')}],
    'changes':'Render current run/receipt before awaiting its separate event log; retain both identity/epoch checks.'}
(folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2), encoding='utf-8')
print(folder)
