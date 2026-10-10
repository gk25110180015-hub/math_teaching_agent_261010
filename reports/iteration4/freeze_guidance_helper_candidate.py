"""Freeze validated reports-only candidates and append a classification correction."""
import hashlib
import json
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--validation', default='repair-guidance-validation/20260922T150012-787500')
    parser.add_argument('--expected-test-count', type=int, default=145)
    args = parser.parse_args()
    validation = REPORTS / args.validation
    result = json.loads((validation / 'result.json').read_bytes())
    assert result['returncode'] == 0 and result['new_windows_compile'] == 'PASS'
    tests = list(ET.parse(validation / 'junit.xml').iter('testcase'))
    assert len(tests) == args.expected_test_count and all(not list(node) for node in tests)
    entries = [('src/math_agent/repair_guidance.py', 'repair_guidance.candidate.py'),
               ('src/math_agent/pipeline.py', 'repair-guidance-pipeline.candidate.py'),
               ('tests/test_repair_guidance.py', 'test_repair_guidance.candidate.py')]
    files = []
    for target, candidate in entries:
        source = ROOT / target; proposed = REPORTS / candidate
        assert result['candidates'][candidate] == sha(proposed)
        files.append({'source': target, 'candidate': candidate,
                      'baseline_sha256': sha(source) if source.exists() else None, 'candidate_sha256': sha(proposed)})
    edits = json.loads((REPORTS / 'repair-guidance-pipeline-edits.json').read_bytes())
    assert files[1]['baseline_sha256'] == edits['baseline_sha256']
    manifest = {'status': 'READY_FOR_REVIEWED_DEPLOYMENT', 'files': files,
                'validation': {'result': str((validation / 'result.json').relative_to(REPORTS)),
                               'tests_passed': len(tests), 'new_tests': len(tests) - 126, 'live_api_calls': 0,
                               'windows_compile_tests_passed': 1, 'teacher_review': 'NOT_RUN'},
                'note': 'Pipeline candidate contains four narrow edits; merge alongside concurrent approved patches.'}
    destination = REPORTS / 'repair-guidance-helper-manifest.json'
    if destination.exists():
        previous = destination.read_bytes()
        archive = REPORTS / ('repair-guidance-helper-manifest-history-' + hashlib.sha256(previous).hexdigest()[:16] + '.json')
        if not archive.exists(): archive.write_bytes(previous)
        else: assert archive.read_bytes() == previous
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    old = REPORTS / 'repair-guidance-validation/20260922T145805-678200'
    node = next(node for node in ET.parse(old / 'junit.xml').iter('testcase') if node.get('name') == 'test_strict_local_patch_is_rechecked_then_actually_compiled_on_windows')
    assert not list(node)
    (old / 'classification-correction.json').write_text(json.dumps({'original_result_preserved': True,
        'correction': 'The runner incorrectly labeled all compilation NOT_RUN. This selected Windows compile test did execute and PASS; models remained injected mocks.',
        'actual_windows_compile_test': node.get('name'), 'result': 'PASS', 'junit_sha256': sha(old / 'junit.xml')}, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
