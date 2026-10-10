"""Run a bounded RED/GREEN real-Edge regression with mock models only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from xml.etree import ElementTree

from run_final_deployed_e2e import source_hashes, archive_databases

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mode',choices=['red','green'],required=True)
args=parser.parse_args()
stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
output=REPORTS/'feedback-poll-validation'/(args.mode+'-'+stamp)
output.mkdir(parents=True,exist_ok=False)
runtime=ROOT/'workspace/t'/('poll-'+stamp[-6:])
before=source_hashes()
env={k:v for k,v in os.environ.items() if not k.startswith('MATH_AGENT_') and k!='OPENAI_API_KEY'}
env.update(MATH_AGENT_API_KEY='',MATH_AGENT_DEEPSEEK_API_KEY='',MATH_AGENT_LIVE_API_ENABLED='false',
    MATH_AGENT_E2E_EVIDENCE_ROOT=str(output),PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1')
if args.mode=='green':env['MATH_AGENT_E2E_APP_JS_CANDIDATE']=str(REPORTS/'feedback-poll-candidate/app.candidate.js')
command=[sys.executable,'-m','pytest',str(REPORTS/'feedback-poll-candidate/test_feedback_receipts_candidate.py'),
         '-q','--basetemp',str(runtime),'--junitxml',str(output/'pytest.xml')]
print('EVIDENCE='+str(output),flush=True)
with (output/'pytest.log').open('x',encoding='utf-8') as stream:
    completed=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=600,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
after=source_hashes()
suites=ElementTree.parse(output/'pytest.xml').getroot().findall('testsuite')
counts={key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
result={'mode':args.mode,'pytest_exit_code':completed.returncode,'junit':counts,
        'source_and_tests_unchanged':before==after,'source_hashes':before,
        'database_snapshots':archive_databases(runtime,output),'real_edge':'EXECUTED',
        'model_provider':'MOCK','real_api':'NOT_RUN','teacher_review':'NOT_RUN'}
result['expected_result_observed']=(before==after and counts=={'tests':1,'failures':int(args.mode=='red'),'errors':0,'skipped':0})
(output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('source_hashes','database_snapshots')},ensure_ascii=False))
raise SystemExit(0 if result['expected_result_observed'] else 1)
