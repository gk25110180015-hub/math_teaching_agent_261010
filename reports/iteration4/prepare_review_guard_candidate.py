"""Build isolated deployable candidates/manifests; never writes production."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


baseline = ROOT / 'src/math_agent/pipeline.py'
assert sha(baseline) == '504e66ea5d2abaec818deafa3420ec70db82fbdee59638fed1c64e8383250fa8'
feedback = OUT / 'recheck-feedback-pipeline.candidate.py'
assert sha(feedback) == '43058915b1775a9236d0a98732aa8131c4f2eecddbdf09802a14d7ad14b34695'
text = feedback.read_text(encoding='utf-8')
start = text.index('    def review_units(')
end = text.index('    def writer_draft(', start)
method = text[start:end]
needle = '        for attempt in range(self.settings.max_local_repair_attempts+1):\n'
assert method.count(needle) == 1
method = method.replace(needle, "        from .review_evidence_attribution import EvidenceAttributionGuard\n"
    "        guard=EvidenceAttributionGuard(self,payload,evidence_dir,label)\n"
    "        replayed=guard.replay()\n"
    "        if replayed is not None:return replayed\n" + needle)
assert method.count('                return review\n') == 1
method = method.replace('                return review\n', '                return guard.inspect(review,accepted_payload=payload)\n')
text = text[:start] + method + text[end:]
needle = "                 'parsing.py','compiler.py','compile_recovery.py','calculation_protocol.py','local_recovery.py')"
assert text.count(needle) == 1
text = text.replace(needle, "                 'parsing.py','compiler.py','compile_recovery.py','calculation_protocol.py','local_recovery.py',\n"
    "                 'review_evidence_attribution.py')")
needle = "        domain_checker=Path(__file__).with_name('series_domain_text.py')"
assert text.count(needle) == 1
text = text.replace(needle, "        from .review_evidence_attribution import attribution_contract\n" + needle)
needle = "            'review_schema_hash':digest(MathReview.model_json_schema()),"
assert text.count(needle) == 1
text = text.replace(needle, needle + "\n            'review_attribution_contract':attribution_contract(),")
candidate = OUT / 'review-evidence-feedback-pipeline.candidate.py'
candidate.write_text(text, encoding='utf-8', newline='\n')
patch = ''.join(difflib.unified_diff(baseline.read_text(encoding='utf-8').splitlines(True), text.splitlines(True),
    fromfile='a/src/math_agent/pipeline.py', tofile='b/src/math_agent/pipeline.py'))
(OUT / 'review-evidence-feedback-pipeline.patch').write_text(patch, encoding='utf-8', newline='\n')
files = []
for source, name in [
    ('src/math_agent/pipeline.py', candidate.name),
    ('src/math_agent/review_evidence_attribution.py', 'review-evidence-attribution.candidate.py'),
    ('src/math_agent/prompts/review_evidence_attribution.md', 'review_evidence_attribution.candidate.md'),
]:
    path = ROOT / source
    files.append({'source': source, 'candidate': name, 'baseline_sha256': sha(path) if path.exists() else None,
                  'candidate_sha256': sha(OUT / name)})
save(OUT / 'review-evidence-attribution-manifest.json', {'status': 'CANDIDATE_NOT_DEPLOYED', 'files': files,
    'production_changes': 0, 'api_calls': 0, 'feedback_pipeline_included': True,
    'schema_location': 'src/math_agent/review_evidence_attribution.py',
    'global_patch_contract_changed': False})

captured = json.loads((OUT / 'CH03-S04-round3-local-followup.json').read_bytes())
actual = {'case_id': 'saved_ch03_cross_unit_misattribution',
    'original_review': captured['reviews'][0]['value'],
    'units': captured['versions']['local_normalized']['value']['units'],
    'prior_sections': [{'section_id': 'S02', 'units': [{'id': 'S02.U03', 'kind': 'proof',
        'tex': captured['misattributed_proof']['actual_proof'], 'relates_to': None}]}],
    'expected': {'disposition': 'misattributed_or_withdrawn', 'remaining_target_blocking': False,
                 'preserve_other_original_issues': True},
    'source_evidence': {'snapshot': 'CH03-S04-round3-local-followup.json',
        'snapshot_sha256': sha(OUT / 'CH03-S04-round3-local-followup.json'),
        'description': 'Exact target units and original real response; prior excerpt from the archived S02.U03 proof. This reduced controlled probe is not full live-run context.'}}
phrase = '应用商的极限法则时必须保证分母的极限存在且为非零实数。'
target = r'令 $f(x)=x$、$g(x)=x^2$，当 $x\to0$ 时二者极限都是 $0$。直接用商的极限法则得 $\lim_{x\to0}f(x)/g(x)=0$。'
legitimate = {'case_id': 'legitimate_dependency_with_misattributed_quote',
    'original_review': {'issues': [{'unit_id': 'S04.U05', 'severity': 'blocking',
        'message': '目标在分母极限为零时错误使用商法则，所称极限为0不成立；同时引用归属需核对。',
        'evidence': 'S04.U05：『' + phrase + '』；目标给出的分母极限是0，不能应用该先修商法则。'}],
        'checked_unit_ids': ['S04.U05'], 'limitations': ['Synthetic dependency control, not teacher review.']},
    'units': [{'id': 'S04.U05', 'kind': 'solution', 'tex': target, 'relates_to': None}],
    'prior_sections': [{'section_id': 'S02', 'units': [{'id': 'S02.U01', 'kind': 'theorem', 'tex': phrase, 'relates_to': None}]}],
    'expected': {'allowed_dispositions': ['target_supported', 'dependency_supported'], 'remaining_target_blocking': True}}
save(OUT / 'review-evidence-attribution-fixtures.json', {'schema_version': 1,
    'cases': [actual, legitimate], 'evaluation': 'TARGETED_REGRESSION_NOT_BLIND_TEST_OR_MODEL_TRAINING'})
print(json.dumps({'manifest': str(OUT / 'review-evidence-attribution-manifest.json'), 'files': files}, ensure_ascii=False))
