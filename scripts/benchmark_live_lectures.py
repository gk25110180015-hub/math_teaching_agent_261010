"""Opt-in resumable API benchmark; default mode reads reference PDFs only."""
import argparse
import json
from pathlib import Path
import sys

from math_agent.benchmark import BenchmarkRunner
from math_agent.settings import Settings, PROJECT_ROOT
from math_agent.util import scrub, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['smoke','chapters','all'],default='smoke')
    parser.add_argument('--run-dir',type=Path,default=PROJECT_ROOT/'reports/iteration2/live-lectures')
    parser.add_argument('--workspace',type=Path,default=None)
    parser.add_argument('--execute-live',action='store_true',help='Send actual charged API requests through Service/Worker')
    parser.add_argument('--retry-failed',action='store_true',help='Resume failed jobs with their original approvals/checkpoints')
    parser.add_argument('--analyze-only',action='store_true',help='Read original/local PDFs and existing run state only')
    parser.add_argument('--per-run-budget',type=int,default=60)
    parser.add_argument('--total-budget',type=int,default=240)
    args=parser.parse_args()
    if args.analyze_only and args.execute_live:
        parser.error('--analyze-only cannot be combined with --execute-live')
    if not 1<=args.per_run_budget<=1000 or not 1<=args.total_budget<=4000:
        parser.error('Request budgets must be positive and bounded')
    state_path=args.run_dir/'benchmark_state.json'
    persisted=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else None
    workspace=args.workspace or (Path(persisted['workspace']) if persisted else PROJECT_ROOT/'workspace/iteration2-live')
    settings=Settings(workspace=workspace,max_requests_per_run=args.per_run_budget)
    runner=None
    try:
        runner=BenchmarkRunner(settings,args.run_dir,per_run_budget=args.per_run_budget,total_budget=args.total_budget)
        result=runner.run(args.phase,execute_live=args.execute_live,retry_failed=args.retry_failed)
        print(json.dumps(result,ensure_ascii=True))
        return 0 if not args.execute_live or all(c['status']=='AWAITING_USER_REVIEW' for c in result['cases']) else 2
    except (Exception,KeyboardInterrupt) as exc:
        error={'status':'INTERRUPTED' if isinstance(exc,KeyboardInterrupt) else 'FAILED',
            'error_type':type(exc).__name__,'message':scrub(str(exc)),'teacher_visual_review':'NOT_RUN',
            'recovery':'Keep this run directory and workspace. Resume after lease expiry and condition repair; external calls at crash boundary may already be billed.'}
        write_json(args.run_dir/'driver_failure.json',error)
        if runner:
            runner.save()
        print(json.dumps(error,ensure_ascii=True),file=sys.stderr)
        return 130 if isinstance(exc,KeyboardInterrupt) else 2


if __name__=='__main__':
    raise SystemExit(main())
