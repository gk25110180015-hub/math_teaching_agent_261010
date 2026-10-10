"""Read the failed run snapshot and compile separate candidates without model calls."""
import json
import sqlite3
import sys
from pathlib import Path

from math_agent.beamer_layout import build_measured_beamer
from math_agent.compiler import TexCompiler
from math_agent.settings import PROJECT_ROOT
from math_agent.util import digest

rid = 'a1a97686646148f096c5d389d0cd00df'
workspace = PROJECT_ROOT / 'workspace'
with sqlite3.connect(workspace.joinpath('agent.db').as_uri() + '?mode=ro', uri=True) as connection:
    connection.row_factory = sqlite3.Row
    connection.execute('BEGIN')
    run = dict(connection.execute('SELECT * FROM runs WHERE id=?', (rid,)).fetchone())
    row = connection.execute('SELECT * FROM plans WHERE run_id=? AND revision=?', (rid, run['active_plan_revision'])).fetchone()
    plan = {**json.loads(row['canonical_json']), 'hash': row['hash']}
payload = json.loads(run['input_json'])
snapshot_hash = digest([payload['parsed'], plan])
output = PROJECT_ROOT / sys.argv[1]
assert output.resolve().is_relative_to(PROJECT_ROOT / 'workspace')
output.mkdir(parents=True, exist_ok=False)
compiler = TexCompiler()

def compile_candidate(source, entry, build):
    result = compiler.compile(source, entry, build, trusted=payload['trusted_input'])
    print(json.dumps({'build': build.name, 'status': result['status'],
        'issues': [{'rule_id': issue['rule_id'], 'message': issue.get('message')} for issue in result['issues']]}, ensure_ascii=False), flush=True)
    return result

source, rendered, fidelity, compiled, inspection = build_measured_beamer(
    payload['parsed'], plan, output, PROJECT_ROOT.parent, compile_candidate,
    lambda status, stage: print(stage, flush=True))
assert snapshot_hash == digest([payload['parsed'], plan])
result = {'run_id': rid, 'source': str(source), 'compile': compiled['status'],
    'fidelity': fidelity['status'], 'inspection': inspection, 'issues': compiled['issues'],
    'frame_count': len(rendered['frame_plan']), 'model_calls': 'NONE', 'original_db': 'READ_ONLY'}
(output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in result.items() if key != 'inspection'}, ensure_ascii=False), flush=True)
if compiled['status'] != 'PASS' or fidelity['status'] != 'PASS' or not inspection or inspection['status'] == 'FAIL':
    raise SystemExit(1)
