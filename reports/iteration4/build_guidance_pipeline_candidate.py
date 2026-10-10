"""Build a reports-only narrow pipeline candidate; no production edits."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main():
    source = ROOT / 'src/math_agent/pipeline.py'
    value = source.read_text(encoding='utf-8')
    patches = [
        ("        state=self._load_global_repair_state(plan)\n", "        state=self._load_global_repair_state(plan)\n        from .repair_guidance import prepare_guidance_resume\n        prepare_guidance_resume(self,plan,state)\n"),
        ("'review_evidence_attribution.py','global_repair_contract.py')", "'review_evidence_attribution.py','global_repair_contract.py','repair_guidance.py')"),
        ("            if (cached and sid not in forced_sections and snapshot['input_hash']==cache_key\n", "            from .repair_guidance import has_requested_guidance\n            pending_guidance=has_requested_guidance(self,plan,sid)\n            if (cached and not pending_guidance and sid not in forced_sections and snapshot['input_hash']==cache_key\n"),
        ("            else:generated=resumed\n            report = None\n", "            else:generated=resumed\n            from .repair_guidance import apply_requested_guidance\n            guided=apply_requested_guidance(self,plan,spec,generated,recovery,draft,[g for _,g in completed])\n            if guided is not None:generated,normalization=guided\n            report = None\n"),
    ]
    for old, new in patches:
        assert value.count(old) == 1, old
        value = value.replace(old, new, 1)
    ast.parse(value)
    (OUT / 'repair-guidance-pipeline.candidate.py').write_text(value, encoding='utf-8')
    (OUT / 'repair-guidance-pipeline-edits.json').write_text(json.dumps({'baseline_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'edits': [{'old': old, 'new': new} for old, new in patches]}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Reports-only pipeline candidate created.')


if __name__ == '__main__':
    main()
