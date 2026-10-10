"""Run the preserved archival fixtures against the deployed package, offline."""
import hashlib
from pathlib import Path

original = Path(__file__).with_name('verify_workflow_recovery_collector.py')
source = original.read_text(encoding='utf-8')
old = "PACKAGE=REPORTS/'uncertainty-protocol-candidate/validation/package'"
assert source.count(old) == 1
source = source.replace(old, "PACKAGE=ROOT/'src'", 1)
print('original_runner_sha256=' + hashlib.sha256(original.read_bytes()).hexdigest())
print('Only validator package selection changes; fixtures/assertions unchanged.', flush=True)
exec(compile(source, str(original), 'exec'), {'__file__': str(original), '__name__': '__main__'})
