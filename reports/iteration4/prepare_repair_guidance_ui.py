"""Build reports-only guidance UI atop the frozen polling recovery candidate."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
REPORTS=Path(__file__).resolve().parent
base=REPORTS/'feedback-poll-candidate/app.candidate.js'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(base)=='09357e0812a2638da48b95f085054e74c47feee422f367c1c40bde4a23956a1b'
text=base.read_text(encoding='utf-8')
changes=[('recheckFeedback: {}, selected:', 'recheckFeedback: {}, repairGuidance: {}, selected:'),
         ('run.feedback_review]);','run.feedback_review, run.repair_guidance_context]);'),
         ('  renderExecution(run);\n  renderFeedbackReview(run);','  renderExecution(run);\n  renderRepairGuidance(run);\n  renderFeedbackReview(run);'),
         ('function renderFeedbackReview(run) {',(REPORTS/'repair-guidance-ui.fragment.js').read_text(encoding='utf-8')+'\nfunction renderFeedbackReview(run) {')]
for old,new in changes:
    assert text.count(old)==1,old
    text=text.replace(old,new,1)
target=REPORTS/'app-repair-guidance.candidate.js'
assert not target.exists()
target.write_text(text,encoding='utf-8')
manifest={'status':'CANDIDATE_NOT_TESTED','base_candidate':'feedback-poll-candidate/app.candidate.js',
    'base_candidate_sha256':sha(base),'files':[{'source':'src/math_agent/web/static/app.js',
    'candidate':target.name,'baseline_sha256':sha(ROOT/'src/math_agent/web/static/app.js'),
    'candidate_sha256':sha(target)}], 'real_api':'NOT_RUN','windows_compile':'NOT_RUN','teacher_review':'NOT_RUN'}
(REPORTS/'repair-guidance-ui-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
