"""Frozen CH02 alias archive RED/GREEN and corruption controls, no network/DB writes."""
from datetime import datetime, timezone
import copy
import json
import os
from pathlib import Path
import runpy
import shutil
import socket
import uuid

for key in list(os.environ):
    if key.startswith('MATH_AGENT_') or key == 'OPENAI_API_KEY': os.environ.pop(key)
attempts = []
def forbidden(*a, **k):
    attempts.append(True)
    raise AssertionError('No network or model calls')
socket.socket.connect = forbidden
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
from math_agent.provider import CompatibleChatProvider
CompatibleChatProvider.generate = forbidden
from math_agent.util import digest, write_json
from workflow_recovery_archive import inspect_uncertainty_migrations

root = Path(__file__).resolve().parents[2]
reports = root / 'reports/iteration4'
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
output = reports / ('historical-migration-collector-' + stamp)
workspace = root / 'workspace/t' / ('hma' + stamp[-6:])
output.mkdir(exist_ok=False)
snapshot = json.loads((reports / 'final-live-evidence/20260924-031540-688381/CH02/database-snapshot.json').read_bytes())
rid = snapshot['run']['id']
source = root / 'workspace/iteration2-live/runs' / rid / 'uncertainty-reviews'
before = {str(p):digest(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
shutil.copytree(source, workspace / 'runs' / rid / 'uncertainty-reviews')
old = runpy.run_path(str(reports / 'collector-history/before-migration-alias-20260924T0318/workflow_recovery_archive.py'))
red = old['inspect_uncertainty_migrations'](workspace, snapshot, output / 'red')
assert not red['all_files_verified']
green = inspect_uncertainty_migrations(workspace, snapshot, output / 'green')
assert green['all_files_verified'] and len(green['records']) == 2
assert all(r['disposition_counts'] == {'resolved_by_current_body': 1} for r in green['records'])
event = next(e for e in snapshot['events'] if e['type'] == 'math.uncertainty_migrated')
state_path = workspace / json.loads(event['payload_json'])['evidence_key']
original_state = state_path.read_bytes()
state = json.loads(original_state)
assessment = state_path.with_name('assessment.json')
original_assessment = assessment.read_bytes()
changed = json.loads(original_assessment)
changed['items'][0]['reason'] = 'Changed assessment must not be accepted even with a refreshed file SHA.'
write_json(assessment, changed)
state['dependencies']['assessment.json'] = digest(assessment.read_bytes())
write_json(state_path, state)
negative = inspect_uncertainty_migrations(workspace, snapshot, output / 'altered-assessment')
assert not negative['all_files_verified']
state_path.write_bytes(original_state)
assessment.write_bytes(original_assessment)
duplicate = copy.deepcopy(snapshot)
duplicate['events'].append(copy.deepcopy(event))
bad_event = inspect_uncertainty_migrations(workspace, duplicate, output / 'duplicate-event')
assert not bad_event['all_files_verified']
assert before == {str(p):digest(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
assert not attempts
result = {'status':'PASS','controls':['old reader rejects historical contract','current reader verifies both exact same-source migrations',
    'changed assessment rejected despite refreshed dependency SHA','duplicate migration receipt rejected'],
    'production_source_evidence_unchanged':True,'external_attempts':len(attempts),'model_calls':0,'database_mutations':0,
    'teacher_review':'NOT_RUN','helper_sha256':digest((reports/'workflow_recovery_archive.py').read_bytes())}
write_json(output / 'result.json', result)
print(json.dumps({'report':str(output/'result.json'),**result},ensure_ascii=False))
