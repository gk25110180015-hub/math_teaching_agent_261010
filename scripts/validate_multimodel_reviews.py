"""Opt-in same-input positive/negative review controls across three live models."""
import argparse
import json
from pathlib import Path

import math_agent.provider as provider_module
from math_agent.domain import MathReview
from math_agent.provider import CompatibleChatProvider
from math_agent.settings import Settings, PROJECT_ROOT
from math_agent.util import AgentError, digest, now, write_json
from benchmark_review_context import classify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--prompt-file', type=Path,
                        help='Optional candidate reviewer prompt, copied into this isolated report; does not edit product prompts.')
    args=parser.parse_args()
    output=args.output_dir.resolve()
    if not output.is_relative_to((PROJECT_ROOT/'reports').resolve()) or output.exists():
        parser.error('Choose a new output directory within project reports.')
    if not args.execute_live:
        print('NOT_RUN: --execute-live and configured environment required.')
        return 0
    settings=Settings().model_copy(update={'max_network_retries':0,'max_schema_repair_attempts':1})
    if not settings.live_api_enabled:
        parser.error('Live API is disabled in the environment.')
    output.mkdir(parents=True)
    fixture_path=PROJECT_ROOT/'reports/iteration2/review-context-calibration-fixtures.json'
    cases=json.loads(fixture_path.read_text(encoding='utf-8'))['cases'][:2]
    write_json(output/'fixtures-local-only.json',cases)
    original_prompts=provider_module.PROMPTS
    frozen=output/'prompts'; frozen.mkdir()
    prompt_source=(args.prompt_file or original_prompts/'reviewer_math.md').resolve()
    prompt=prompt_source.read_bytes()
    (frozen/'reviewer_math.md').write_bytes(prompt)
    provider_module.PROMPTS=frozen
    state={'created_at':now(),'status':'RUNNING','request_limit':12,'request_count':0,
        'model_order':['gpt6','deepseek-flash','deepseek-v4-pro'],'automatic_fallback':False,
        'prompt_sha256':digest(prompt),'prompt_source':str(prompt_source),'fixture_sha256':digest(fixture_path.read_bytes()),
        'requests':[],'results':[],'teacher_review':'NOT_RUN','expectations_sent':False,
        'existing_runs_modified':False,'model_weight_training':False,
        'scope':'Two authored controls per model; not a random benchmark or general accuracy estimate.'}
    active={'case_id':None,'model_id':None}
    def save(): write_json(output/'state.json',state)
    def before(metadata):
        if state['request_count']>=state['request_limit']:
            raise AgentError('BUDGET_EXHAUSTED','Twelve-request local validation limit reached')
        if digest((frozen/'reviewer_math.md').read_bytes())!=state['prompt_sha256']:
            raise AgentError('PROMPT_CHANGED','Frozen review prompt changed')
        state['request_count']+=1
        state['requests'].append({'type':'request','number':state['request_count'],**active,**metadata})
        save()
    def record(metadata):
        state['requests'].append({'type':'result','number':state['request_count'],**active,**metadata})
        save()
    save()
    try:
        for model_id in state['model_order']:
            for case in cases:
                active.update(case_id=case['id'],model_id=model_id)
                entry={'model_id':model_id,'case_id':case['id'],'expected_kind':case['expectation']['kind'],
                    'started_at':now(),'profile':settings.model_profile(model_id)}
                try:
                    provider=CompatibleChatProvider(settings,preferred_model=model_id,allow_fallback=False,
                        before_request=before,record=record,failure_dir=output/model_id/case['id']/'invalid')
                    # Only input is transmitted. Expectations and case classification remain local.
                    review=provider.generate('reviewer_math',case['input'],MathReview)
                    write_json(output/model_id/(case['id']+'-review.json'),review)
                    entry.update(status='RESPONSE_VALIDATED',**classify(review,case),
                        actual_response=getattr(provider,'last_response_metadata',{}))
                except AgentError as exc:
                    entry.update(status='BLOCKED',classification_status='NOT_RUN',error={'code':exc.code,'message':exc.message})
                entry['finished_at']=now()
                state['results'].append(entry);save()
                print(json.dumps({'model_id':model_id,'case_id':case['id'],'status':entry['status'],
                    'classification':entry['classification_status'],'requests_so_far':state['request_count']},ensure_ascii=True),flush=True)
        state['status']='PASS' if all(row['classification_status']=='PASS' for row in state['results']) else 'NEEDS_REVIEW'
        state['finished_at']=now();save()
        return 0 if state['status']=='PASS' else 2
    finally:
        provider_module.PROMPTS=original_prompts
        save()


if __name__=='__main__':
    raise SystemExit(main())
