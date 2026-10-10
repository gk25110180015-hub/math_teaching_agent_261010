"""Opt-in live or offline full visualization workflow; never submits custom suggestions."""
import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4
from math_agent.settings import Settings, PROJECT_ROOT
from math_agent.service import Service
from math_agent.worker import Worker
from math_agent.domain import NewRun, ConfirmRequest, ExecuteRequest
from math_agent.visualization.models import RefineRequest
from math_agent.visualization.service import refine
from math_agent.util import write_json


def identity(plan):
    return {'expected_plan_revision': plan['revision'], 'expected_plan_hash': plan['hash']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--topic',action='append')
    parser.add_argument('--model',default='gpt6')
    parser.add_argument('--workspace')
    args=parser.parse_args()
    root=PROJECT_ROOT/'reports/visualization-20260928'/('live-' if args.live else 'mock-')/uuid4().hex[:8]
    root.mkdir(parents=True)
    workspace=Path(args.workspace).resolve() if args.workspace else root/'runtime'
    settings=Settings(workspace=workspace, max_requests_per_run=35, llm_read_timeout_seconds=600, llm_total_timeout_seconds=900)
    service=Service(settings,actor='benchmark_driver'); worker=Worker(settings)
    result={'mode':'live' if args.live else 'mock','workspace':str(workspace),'runs':[], 'custom_suggestions':'SKIPPED_AS_REQUESTED','teacher_review':'NOT_RUN'}
    write_json(root/'result.json',result)
    for topic in args.topic or ['导数','梯度下降算法']:
        rid=service.create(NewRun(workflow_id='visualization.create',topic=topic,provider='live' if args.live else 'mock',model_id=args.model,trusted_input=True))['id']
        entry={'topic':topic,'run_id':rid};result['runs'].append(entry)
        write_json(root/'result.json', result)
        service.propose(rid)
        for round in range(8):
            worker.tick();run=service.get(rid);plan=run['plan']
            print(json.dumps({'topic':topic,'status':run['status'],'round':round,'requests':run['request_count']},ensure_ascii=False),flush=True)
            write_json(root/(rid+'.json'),run)
            if run['status'] in ('FAILED','BLOCKED','CANCELLED'):
                break
            if round == 7 and (plan['phase'] == 'candidates' or plan['questions']):
                entry['driver_limit'] = 'Eight planning rounds reached; no further job enqueued.'
                break
            if plan['phase']=='candidates':
                refine(service,rid,RefineRequest(**identity(plan),candidate_id=plan['candidates'][0]['id']))
            elif plan['questions']:
                refine(service,rid,RefineRequest(**identity(plan),answers={q['id']:q['options'][0]['id'] for q in plan['questions']}))
            else:
                service.confirm(rid,ConfirmRequest(**identity(plan),action_id=uuid4().hex))
                service.execute(rid,ExecuteRequest(**identity(plan),idempotency_key=uuid4().hex))
                worker.tick();run=service.get(rid);break
        entry.update(status=run['status'],error=run.get('error'),requests=run['request_count'])
        write_json(root/(rid+'.json'),run)
        write_json(root/'result.json',result)
        print(json.dumps(entry,ensure_ascii=False),flush=True)
    print(str(root/'result.json'),flush=True)
    return 0 if all(r['status']=='COMPLETED_WITH_WARNINGS' for r in result['runs']) else 1


if __name__=='__main__':sys.exit(main())
