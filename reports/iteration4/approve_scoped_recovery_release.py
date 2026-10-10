"""Attach exact combined validation evidence to an undeployed candidate."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('validation', type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve(); validation = args.validation.resolve()
    assert manifest_path.is_relative_to(REPORTS) and validation.is_relative_to(REPORTS)
    result = json.loads((validation/'result.json').read_bytes())
    assert result['status'] == 'PASS' and result['production_unchanged'] and not result['external_network_attempts']
    context = json.loads((validation/'context.json').read_bytes())
    assert context['manifest_sha256'] == sha(manifest_path)
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest['status'] == 'PENDING_COMBINED_VALIDATION'
    for item in manifest['files']:
        assert sha(REPORTS/item['candidate']) == item['candidate_sha256']
        original = ROOT/item['source']
        assert (sha(original) if original.exists() else None) == item['baseline_sha256']
    nodes = list(ET.parse(validation/'pytest.xml').iter('testcase'))
    assert nodes and all(node.find('failure') is None and node.find('error') is None for node in nodes)
    manifest.update(status='READY_FOR_REVIEWED_DEPLOYMENT', reviewed_at=datetime.now(timezone.utc).isoformat(),
        combined_validation={'path': validation.relative_to(REPORTS).as_posix(),
            'passed': sum(node.find('skipped') is None for node in nodes), 'result': result},
        independent_reviews=['uncertainty-protocol-independent-audit.md',
            'repair-guidance-api-independent-audit.md', 'scoped-guidance-root-audit.md'])
    destination = manifest_path.with_name('ready-manifest.json')
    assert not destination.exists()
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'manifest': destination.relative_to(REPORTS).as_posix(), 'passed': manifest['combined_validation']['passed']}))


if __name__ == '__main__':
    main()
