"""Read-only replay of actual CH02 evidence using the isolated tested candidate."""
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];REPORTS=ROOT/'reports/iteration4'
validation=REPORTS/'combined-recovery-validation/20260923-150326-99eba1'
context=json.loads((validation/'context.json').read_bytes());result=json.loads((validation/'result.json').read_bytes())
assert result['status']=='PASS' and result['production_unchanged'] and not result['external_network_attempts']
sys.dont_write_bytecode=True;sys.path.insert(0,str(Path(context['package'])/'src'))
from math_agent.uncertainty_review import UncertaintyReview
from math_agent.uncertainty_protocol_recovery import legacy_replay
from math_agent.util import digest
import math_agent.uncertainty_protocol_recovery as module
assert Path(module.__file__).resolve().is_relative_to(Path(context['package']).resolve())
WS=ROOT/'workspace/iteration2-live';RID='fd6736af6ef14be3839e019e86ca1e5c'
class ReadOnlyStore:
    @contextmanager
    def connect(self):
        with sqlite3.connect((WS/'agent.db').as_uri()+'?mode=ro',uri=True) as c:
            c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
            yield c
            c.rollback()
p=SimpleNamespace(settings=SimpleNamespace(workspace=WS),root=WS/'runs'/RID,
    build_root=WS/'b'/RID[:16],run={'id':RID},store=ReadOnlyStore())
old=p.root/'uncertainty-reviews/73561f56541cf8d39383e863'
alias=p.root/'uncertainty-reviews/68732aa43118b16ab677b379'
frozen=json.loads((old/'input.json').read_bytes())
state=json.loads((p.root/'local-repair/S02.json').read_bytes())
assert json.loads((WS/state['candidate_key']).read_bytes())==frozen['section']
for section in frozen['prior_sections']:
    prior=json.loads((p.root/'local-repair'/(section['section_id']+'.json')).read_bytes())
    assert json.loads((WS/prior['candidate_key']).read_bytes())==section
before={str(f):digest(f.read_bytes()) for folder in (old,alias) for f in folder.iterdir()}
guard=UncertaintyReview(p,frozen)
replay=legacy_replay(guard)
assert replay['assessment.json']==json.loads((alias/'assessment.json').read_bytes())
assert before=={str(f):digest(f.read_bytes()) for folder in (old,alias) for f in folder.iterdir()}
assert not guard.path.exists()
report={'at':datetime.now(timezone.utc).isoformat(),'status':'PASS_READ_ONLY_REPLAY',
    'run_id':RID,'source':replay['source'],'assessment_sha256':digest(replay['assessment.json']),
    'aliased_state_sha256':digest((alias/'state.json').read_bytes()),'actual_current_body_matches':True,
    'original_files_unchanged':True,'new_model_calls':0,'database_mutations':0,
    'dispositions':[{'unit_id':i['unit_id'],'disposition':i['disposition']} for i in replay['assessment.json']['items']],
    'production_workflow_resume':'NOT_RUN_BY_THIS_SCRIPT','teacher_review':'NOT_RUN'}
with (REPORTS/'uncertainty-alias-candidate/actual-readonly-replay.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
manifest_path=REPORTS/'uncertainty-alias-candidate/manifest.json'
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest()==context['manifest_sha256']
m=json.loads(manifest_path.read_bytes())
for item in m['files']:
    assert hashlib.sha256((REPORTS/item['candidate']).read_bytes()).hexdigest()==item['candidate_sha256']
    source=ROOT/item['source'];assert (hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else None)==item['baseline_sha256']
m.update(status='READY_FOR_REVIEWED_DEPLOYMENT',validation={'path':str(validation),'passed':156,'new_tests':20,'external_network_attempts':0},
    actual_replay='actual-readonly-replay.json',review='UNCERTAINTY_ALIAS_RECOVERY.md')
with (REPORTS/'uncertainty-alias-candidate/ready-manifest.json').open('x',encoding='utf-8') as f:json.dump(m,f,ensure_ascii=False,indent=2)
print(json.dumps(report,ensure_ascii=False))
