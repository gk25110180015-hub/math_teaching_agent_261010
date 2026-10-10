"""Combine frozen, independently reviewed candidates without production writes."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid

REPORTS = Path(__file__).resolve().parent
ROOT = REPORTS.parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    names = ['uncertainty-protocol-manifest.json', 'repair-guidance-helper-manifest.json',
        'repair-guidance-api-candidate/ready-manifest.json', 'repair-guidance-ui-manifest.json',
        'feedback-poll-candidate/manifest.json']
    folder = REPORTS / ('scoped-recovery-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6])
    folder.mkdir(exist_ok=False)
    files = {}; manifests = []
    for name in names:
        path = REPORTS / name
        manifest = json.loads(path.read_bytes())
        assert manifest['status'] == 'READY_FOR_REVIEWED_DEPLOYMENT'
        manifests.append({'path': name, 'sha256': sha(path)})
        for item in manifest['files']:
            if name == 'feedback-poll-candidate/manifest.json' and item['source'].endswith('/app.js'):
                continue  # The reviewed guidance UI includes this exact polling change.
            assert item['source'] not in files, item['source']
            original = ROOT / item['source']; candidate = REPORTS / item['candidate']
            assert (sha(original) if original.exists() else None) == item['baseline_sha256']
            assert sha(candidate) == item['candidate_sha256']
            target = folder / item['source']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, target)
            if target.suffix == '.py':
                ast.parse(target.read_text(encoding='utf-8'))
            files[item['source']] = {**item, 'candidate': target.relative_to(REPORTS).as_posix()}
    edits = json.loads((REPORTS/'repair-guidance-pipeline-edits.json').read_bytes())
    original = ROOT/'src/math_agent/pipeline.py'
    assert sha(original) == edits['baseline_sha256']
    value = original.read_text(encoding='utf-8')
    for edit in edits['edits']:
        assert value.count(edit['old']) == 1
        value = value.replace(edit['old'], edit['new'], 1)
    candidate = REPORTS/files['src/math_agent/pipeline.py']['candidate']
    assert value == candidate.read_text(encoding='utf-8'), 'Unexpected pipeline changes'
    # The known v2 global repair identity must stay stable for existing jobs.
    assert sha(ROOT/'src/math_agent/global_repair_contract.py') == '8c1167ba608adbc1b74d9fe4d5852152eba74069606c466a4c2db606c8df2186'
    result = {'status': 'PENDING_COMBINED_VALIDATION', 'source_manifests': manifests,
        'files': list(files.values()), 'pipeline_edits_exact': True,
        'global_contract_unchanged': True, 'production_modified': False, 'teacher_review': 'NOT_RUN'}
    (folder/'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'manifest': (folder/'manifest.json').relative_to(REPORTS).as_posix(), 'files': len(files)}))


if __name__ == '__main__':
    main()
