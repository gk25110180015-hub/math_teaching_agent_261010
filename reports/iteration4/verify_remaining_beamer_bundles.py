"""Finish the four previously unrun clean ZIP builds; keep historical evidence."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import traceback
import uuid

for key in list(os.environ):
    if key.startswith('MATH_AGENT_') or key == 'OPENAI_API_KEY':
        os.environ.pop(key)
root = Path(__file__).resolve().parents[2]
old = root / 'workspace/iteration2-delivery/delivery-20260920-020236.json'
baseline = json.loads(old.read_bytes())
helper = runpy.run_path(str(root / 'reports/iteration2/prepare_deliverables.py'))
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
output = root / 'reports/iteration4' / ('remaining-beamer-bundles-' + stamp)
build = root / 'workspace/t' / ('br' + stamp[-6:])
output.mkdir(exist_ok=False)
build.mkdir(exist_ok=False)
report = {'status': 'RUNNING', 'created_at': datetime.now(timezone.utc).isoformat(),
          'historical_report': str(old), 'historical_report_sha256': hashlib.sha256(old.read_bytes()).hexdigest(),
          'model_calls': 0, 'teacher_visual_review': 'NOT_RUN', 'cases': [], 'errors': []}
try:
    for index, name in enumerate(('CH01-fduclassroom', 'CH02-default', 'CH02-fduclassroom', 'CH03-default'), 1):
        case = next(row for row in baseline['cases'] if row['case'] == name)
        assert case['clean_recompile'] == 'NOT_RUN'
        archive = Path(case['bundle'])
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == case['bundle_sha256']
        manifest = json.loads(Path(case['compile_manifest']).read_bytes())
        original_pdf = Path(case['pdf'])
        pdf_hash = hashlib.sha256(original_pdf.read_bytes()).hexdigest()
        assert pdf_hash == manifest['baseline_pdf']['sha256']
        result = helper['recompile'](case, build, index)
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == case['bundle_sha256']
        assert hashlib.sha256(original_pdf.read_bytes()).hexdigest() == pdf_hash
        report['cases'].append(result)
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    report['status'] = 'PASS' if all(row['status'] == 'PASS' for row in report['cases']) else 'FAIL'
except BaseException as exc:
    report.update(status='FAIL')
    report['errors'].append({'type': type(exc).__name__, 'message': str(exc)})
    (output / 'failure.log').write_text(traceback.format_exc(), encoding='utf-8')
finally:
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(output / 'report.json'),
                      'cases': [{'case': r['case'], 'status': r['status']} for r in report['cases']]}, ensure_ascii=False), flush=True)
raise SystemExit(0 if report['status'] == 'PASS' else 1)
