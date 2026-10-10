"""Build Service/UI candidates only; do not modify deployed sources."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

files = []
diffs = []
for name, rel in [('service', 'src/math_agent/service.py'), ('ui', 'src/math_agent/web/static/app.js')]:
    raw = (ROOT/rel).read_bytes()
    original = raw.decode('utf-8')
    value = original.replace('\r\n', '\n')
    if name == 'service':
        marker = "        run['model_routing'] = routing_summary(self.store, run)\n"
        assert value.count(marker) == 1
        value = value.replace(marker, marker + "        run['feedback_review'] = self.feedback_review(run)\n")
        marker = '    def increase_budget(self, run_id, request):\n'
        assert value.count(marker) == 1
        value = value.replace(marker, (OUT/'feedback-receipts-service-method.txt').read_text(encoding='utf-8') + '\n' + marker)
    else:
        marker = 'run.partial_checkpoints, run.model_routing]);'
        assert value.count(marker) == 1
        value = value.replace(marker, 'run.partial_checkpoints, run.model_routing, run.feedback_review]);')
        marker = '  renderExecution(run);\n'
        assert value.count(marker) == 1
        value = value.replace(marker, marker + '  renderFeedbackReview(run);\n')
        marker = 'function renderArtifacts(run) {\n'
        assert value.count(marker) == 1
        value = value.replace(marker, (OUT/'feedback-receipts-ui-function.txt').read_text(encoding='utf-8') + '\n' + marker)
    candidate = OUT / ('feedback-receipts-' + name + '.candidate' + Path(rel).suffix)
    candidate.write_text(value, encoding='utf-8', newline='\n')
    files.append({'source':rel,'baseline_sha256':sha(raw),'candidate':candidate.name,'candidate_sha256':sha(candidate.read_bytes())})
    diffs.extend(difflib.unified_diff(original.replace('\r\n','\n').splitlines(True),value.splitlines(True),fromfile=rel,tofile=rel))
(OUT/'feedback-receipts-api-ui.patch').write_text(''.join(diffs),encoding='utf-8',newline='\n')
(OUT/'feedback-receipts-api-ui-manifest.json').write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'status':'CANDIDATE_UNTESTED','production_modified':False,'files':files},indent=2),encoding='utf-8')
print(json.dumps(files,indent=2))
