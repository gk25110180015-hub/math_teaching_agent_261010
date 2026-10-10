"""One-shot hash-checked composition of independently reviewed candidates."""
import ast
import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()
source = ROOT / 'src/math_agent/pipeline.py'
original = source.read_text(encoding='utf-8')
assert sha(source.read_bytes()) == '350f9eff0d4a8f24937e4c0dfc605f7f2bb928fc603b313d99219553ea628a1c'
combined = REPORT / 'cached-teaching-quality-combined.candidate.py'
assert sha(combined.read_bytes()) == '6cf9b2400220458a1d94147ca7ae8ecfd655f3969a97cb918070dba42c98f5c5'
candidate = combined.read_text(encoding='utf-8')
global_candidate = REPORT / 'global-budget-resume.candidate.py'
global_manifest = json.loads((REPORT / 'global-budget-resume-manifest.json').read_bytes())
assert sha(global_candidate.read_bytes()) == global_manifest['candidate_sha256']


def method(text, name):
    cls = next(node for node in ast.parse(text).body if isinstance(node, ast.ClassDef) and node.name == 'Pipeline')
    node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ''.join(text.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])


for name in ('_import_legacy_global_failure', 'lecture'):
    before = method(original, name)
    assert candidate.count(before) == 1, name
    candidate = candidate.replace(before, method(global_candidate.read_text(encoding='utf-8'), name), 1)

# Apply only the literal, individually reviewed narrow replacement operations.
generator = REPORT / 'prepare-compile-recovery-candidate.py'
operations = []
for statement in ast.parse(generator.read_text(encoding='utf-8')).body:
    if (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name) and statement.value.func.id == 'replace_once'):
        before, after = map(ast.literal_eval, statement.value.args)
        assert candidate.count(before) == 1, before
        candidate = candidate.replace(before, after, 1)
        operations.append({'before_sha256': sha(before.encode()), 'after_sha256': sha(after.encode())})
assert len(operations) == 5
before = "'parsing.py','compiler.py','calculation_protocol.py','local_recovery.py')"
assert candidate.count(before) == 1
candidate = candidate.replace(before, "'parsing.py','compiler.py','compile_recovery.py','calculation_protocol.py','local_recovery.py')", 1)

# A same-plan repair contract change must never silently reset cumulative rounds.
old_load = method(candidate, '_load_global_repair_state')
anchor = '                    return state\n'
assert old_load.count(anchor) == 1
new_load = old_load.replace(anchor, anchor + "                if state['identity'].get('plan_hash')==plan['hash']:\n"
    "                    self._global_repair_sections(state)\n"
    "                    raise AgentError('GLOBAL_REPAIR_CONTRACT_CHANGED','同一批准计划的全局修复契约发生变化；已保留原轮次、候选和疑点，不能静默归零。需恢复原契约或显式迁移状态后继续。')\n")
candidate = candidate.replace(old_load, new_load, 1)
ast.parse(candidate)

helper = REPORT / '待合并/compile_recovery.py'
assert sha(helper.read_bytes()) == 'aad2764ca6751343fb79b4e29ced6822a245584b1782185d928f727b8e3c63ab'
prompt = REPORT / 'reviewer_math_v6.candidate.md'
assert sha(prompt.read_bytes()) == 'cd75bbcf1516a0fa5ecaa882e753956e82d65da7e0640442db98717a1cf6f92d'
prompt_target = ROOT / 'src/math_agent/prompts/reviewer_math.md'
assert sha(prompt_target.read_bytes()) == '5d38a796ccdff81f3bba09d0c48210a836e83b77be5b31c2a814f7437e1ec69a'
helper_target = ROOT / 'src/math_agent/compile_recovery.py'
assert not helper_target.exists()
backup = REPORT / ('merge-pipeline-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
backup.mkdir()
for db in (ROOT / 'workspace/agent.db', ROOT / 'workspace/iteration2-live/agent.db'):
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        assert not conn.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone()
        with sqlite3.connect(backup / (db.parent.name + '-before.db')) as dest:
            conn.backup(dest)
records = []
for target, content in ((source, candidate.encode('utf-8')), (helper_target, helper.read_bytes()), (prompt_target, prompt.read_bytes())):
    rel = target.relative_to(ROOT)
    previous = target.read_bytes() if target.exists() else None
    if previous is not None:
        saved = backup / rel
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(previous)
    target.write_bytes(content)
    records.append({'path': rel.as_posix(), 'before_sha256': sha(previous) if previous else None, 'after_sha256': sha(content)})
manifest = {'files': records, 'compile_replacements': operations, 'jobs_stopped': True,
            'real_api_for_deployed_v6': 'NOT_RUN_YET', 'teacher_review': 'NOT_RUN'}
(backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'backup': str(backup), 'files': records}, ensure_ascii=True))
