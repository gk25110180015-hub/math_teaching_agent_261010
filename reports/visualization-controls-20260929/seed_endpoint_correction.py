"""One reviewed, exact correction to generated code; no plan/approval/budget edits.

Run only with the local worker stopped and no active jobs. The correction is an
unchecked checkpoint: the normal worker MUST repeat runtime/model/render gates.
Historical files are kept intact and the previous delivery is superseded.
"""
import copy
import json
from pathlib import Path
from math_agent.settings import Settings
from math_agent.service import Service
from math_agent.util import digest
from math_agent.visualization.models import Program
from math_agent.visualization.recovery import last_failure, contract_hash

RID='43a4bc7fcb564b7dbd156b482bab5aa7'
PLAN='735b15da3d279fb8e4a3bc17d071f04a7033a478785b8334eb0afe7abeae2249'
s=Service(Settings());run=s.get(RID)
assert run['status']=='COMPLETED_WITH_WARNINGS'
assert run['plan']['hash']==run['approval']['hash']==PLAN
directory=s.settings.workspace/'b/43a4bc7fcb564b7d/visual-ce3daf13'
program=json.loads((directory/'project.json').read_text(encoding='utf-8'))['program']
fixed=copy.deepcopy(program)
before='x0*(x0+h)<=0';after='x0*(x0+h)<0'
assert fixed['code'].count(before)==1
fixed['code']=fixed['code'].replace(before,after)
fixed=Program.model_validate(fixed).model_dump()
evidence={'actor':'codex_debugging','plan_hash':PLAN,'before_program_hash':digest(program),'after_program_hash':digest(fixed),
          'before':before,'after':after,'reason':'Q lands at 0 without crossing the cusp: x0=1, h=-1 has residual=0.',
          'approval_changed':False,'budget_changed':False,'required_checks':'normal runtime/model review/video rendering; no bypass'}
root=Path(__file__).resolve().parent
(root/'endpoint-correction.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
context={'confirmed_plan':run['plan'],'runtime_contract_version':2,**last_failure(s.store,s.settings.workspace,run)}
identity=digest({'context':context,'contract_hash':contract_hash()})
with s.store.transaction() as c:
    assert not c.execute("select 1 from jobs where status in ('queued','running')").fetchone()
    queued=s._enqueue(c,s.store.row(c,RID),'build',digest([RID,PLAN,'verified-endpoint-correction',digest(fixed)]))
    s.store.event(c,RID,'visualization.code.corrected',evidence)
    for artifact in run['artifacts']:
        if artifact['metadata'].get('kind')=='visualization' and artifact['metadata'].get('plan_hash')==PLAN:
            c.execute("update artifacts set status='superseded' where artifact_id=?",(artifact['artifact_id'],))
job=s.store.claim('visualization-correction-seed')
assert job['id']==queued['id']
s.store.checkpoint(job,'visualization.code.0',identity,fixed)
s.store.finish(job,'BLOCKED','visualization.audit.correction',{'code':'VISUAL_AUDIT_CORRECTION',
    'message':'准确修正 Q 到达原点时的分支判定；修正代码仍需通过完整自动检查。'})
s.retry(RID)
current=s.get(RID)
assert current['plan']['hash']==PLAN and current['approval']==run['approval']
assert current['request_count']==run['request_count']
print(json.dumps({'job_id':job['id'],'status':current['status'],'cached_unchecked_code':True,'requests':current['request_count']}))
