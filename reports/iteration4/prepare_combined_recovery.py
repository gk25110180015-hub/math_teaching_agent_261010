"""Combine two frozen reviewed changes in a new report directory; no deployment."""
import ast
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def methods(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return {node.name: ast.dump(node, include_attributes=False)
            for top in tree.body if isinstance(top, ast.ClassDef) and top.name == 'Pipeline'
            for node in top.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def main():
    paths = [REPORTS/'global-strict-patch-manifest.json', REPORTS/'uncertainty-review-manifest.json']
    manifests = [json.loads(p.read_bytes()) for p in paths]
    assert all(m['status'] == 'READY_FOR_REVIEWED_DEPLOYMENT' for m in manifests)
    folder = REPORTS/('combined-recovery-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6])
    folder.mkdir(exist_ok=False)
    entries = {}
    for manifest in manifests:
        for item in manifest['files']:
            original = ROOT/item['source']
            candidate = (REPORTS/item['candidate']).resolve()
            assert candidate.is_relative_to(REPORTS)
            assert sha(candidate) == item['candidate_sha256']
            assert (sha(original) if original.exists() else None) == item['baseline_sha256']
            destination = folder/candidate.name
            assert not destination.exists(), 'Candidate names must be unique'
            shutil.copyfile(candidate, destination)
            if item['source'] in entries:
                assert item['source'] == 'src/math_agent/pipeline.py'
            entries[item['source']] = {**item, 'candidate': destination.relative_to(REPORTS).as_posix()}
    builder = REPORTS/'build_uncertainty_candidates.py'
    shutil.copyfile(builder, folder/'builder-used.py')
    spec = importlib.util.spec_from_file_location('isolated_candidate_builder', builder)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT, module.REPORTS = ROOT, folder
    sys.argv = [str(builder), '--pipeline-base', str(folder/'global-patch-pipeline.candidate.py')]
    with (folder/'merge.log').open('x', encoding='utf-8') as stream:
        with redirect_stdout(stream):
            module.main()
    for name, entry in entries.items():
        observed = sha(REPORTS/entry['candidate'])
        if name != 'src/math_agent/pipeline.py':
            assert observed == entry['candidate_sha256'], 'Unexpected change during merge: ' + name
        else:
            entry['candidate_sha256'] = observed
    base = methods(ROOT/'src/math_agent/pipeline.py')
    global_methods = methods(REPORTS/'global-patch-pipeline.candidate.py')
    doubt_methods = methods(REPORTS/'uncertainty-pipeline.candidate.py')
    combined = methods(REPORTS/entries['src/math_agent/pipeline.py']['candidate'])
    gchanged = {key for key in base if base[key] != global_methods[key]}
    dchanged = {key for key in base if base[key] != doubt_methods[key]}
    overlap = gchanged & dchanged
    assert len(overlap) == 1 and 'contract' in next(iter(overlap))
    assert set(base) == set(combined)
    for key in base:
        if key in overlap:
            continue
        expected = global_methods[key] if key in gchanged else doubt_methods[key] if key in dchanged else base[key]
        assert combined[key] == expected, 'Method was overwritten: ' + key
    result = {'status': 'PENDING_COMBINED_VALIDATION',
        'source_manifests': [{'path': p.name, 'sha256': sha(p)} for p in paths],
        'builder_sha256': sha(builder), 'files': list(entries.values()),
        'merge_checks': {'global_methods': sorted(gchanged), 'uncertainty_methods': sorted(dchanged),
                         'combined_contract': sorted(overlap), 'other_methods_exact': True},
        'production_deployed': False, 'real_api': 'NOT_RUN', 'teacher_review': 'NOT_RUN'}
    target = folder/'reviewed-manifest.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'manifest': target.relative_to(REPORTS).as_posix(),
                      'sha256': sha(target), 'files': len(entries), 'merge_checks': result['merge_checks']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
