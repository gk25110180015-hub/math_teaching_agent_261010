"""Prepare isolated candidates only; never write deployed source."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


pipeline = ROOT / 'src/math_agent/pipeline.py'
assert digest(pipeline) == '96d0f9e042836bf88fb1609159066d7b20113be41a193bbfa6e57f4f4086a683'
text = pipeline.read_text(encoding='utf-8')
text = text.replace('        from .review_evidence_attribution import attribution_contract\n',
    '        from .review_evidence_attribution import attribution_contract\n        from .feedback_review import feedback_contract\n')
text = text.replace("            'review_attribution_contract':attribution_contract(),\n",
    "            'review_attribution_contract':attribution_contract(),\n            'feedback_review_contract':feedback_contract(),\n")
old = "            global_reports.append({'chapter_coverage':coverage,'review':review})\n        return global_reports,issues"
new = """            global_reports.append({'chapter_coverage':coverage,'review':review})
            if feedback and not issues:
                from .feedback_review import FeedbackReview
                self.stage('GLOBAL_REVIEW','teaching.feedback')
                receipt,feedback_issues=FeedbackReview(self,plan,units,feedback).evaluate()
                global_reports.append({'feedback_review':receipt})
                issues.extend(feedback_issues)
        return global_reports,issues"""
assert text.count(old) == 1
text = text.replace(old, new)
(OUT / 'feedback-assessment-pipeline.candidate.py').write_text(text, encoding='utf-8')

provider = ROOT / 'src/math_agent/provider.py'
assert digest(provider) == 'ccdc7b2f3ff58bab30193e3c1db809b8a203a2986f6096a8bfa5d30426daf5d6'
text = provider.read_text(encoding='utf-8')
text = text.replace('        for attempt in range(self.settings.max_schema_repair_attempts + 1):',
    "        schema_attempts = 1 if role == 'reviewer_feedback' else self.settings.max_schema_repair_attempts + 1\n        for attempt in range(schema_attempts):")
needle = "        elif role == 'reviewer_math':\n"
assert text.count(needle) == 1
text = text.replace(needle, "        elif role == 'reviewer_feedback':\n            from .feedback_review import mock_feedback_assessment\n            value = mock_feedback_assessment(context)\n" + needle)
(OUT / 'feedback-assessment-provider.candidate.py').write_text(text, encoding='utf-8')

files = []
for source, candidate in [
    ('src/math_agent/pipeline.py', 'feedback-assessment-pipeline.candidate.py'),
    ('src/math_agent/provider.py', 'feedback-assessment-provider.candidate.py'),
    ('src/math_agent/feedback_review.py', 'feedback_review.candidate.py'),
    ('src/math_agent/prompts/reviewer_feedback.md', 'reviewer_feedback.candidate.md')]:
    target, prepared = ROOT / source, OUT / candidate
    files.append({'source': source, 'candidate': candidate,
        'baseline_sha256': digest(target) if target.exists() else None,
        'candidate_sha256': digest(prepared)})
    original = target.read_text(encoding='utf-8') if target.exists() else ''
    patch = ''.join(difflib.unified_diff(original.splitlines(True), prepared.read_text(encoding='utf-8').splitlines(True),
        fromfile=source, tofile=source))
    (OUT / (candidate + '.patch')).write_text(patch, encoding='utf-8')
(OUT / 'feedback-assessment-manifest.json').write_text(json.dumps({
    'status': 'CANDIDATE_UNDER_TEST', 'files': files,
    'production_modified': False, 'test_classification': 'MOCK_ONLY_PENDING',
    'teacher_review': 'NOT_RUN'}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'files': files}, ensure_ascii=False))
