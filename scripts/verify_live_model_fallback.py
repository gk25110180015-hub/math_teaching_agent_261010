"""Explicit MIXED test: local GPT 504 injection then one real DeepSeek call."""
import argparse
import json
from pathlib import Path
import httpx
from math_agent.provider import CompatibleChatProvider
from math_agent.settings import Settings, PROJECT_ROOT
from math_agent.util import AgentError, now, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-live',action='store_true')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if not args.execute_live:
        print('NOT_RUN: one real DeepSeek request requires --execute-live.')
        return 0
    output=args.output_dir.resolve()
    if output.exists() or not output.is_relative_to((PROJECT_ROOT/'reports').resolve()):
        parser.error('Use a new report directory.')
    settings=Settings().model_copy(update={'max_network_retries':0,'max_schema_repair_attempts':0})
    if not all(settings.model_profile(model)['configured'] for model in ('gpt6','deepseek-flash')):
        parser.error('Both GPT and DeepSeek environment profiles must be enabled.')
    output.mkdir(parents=True)
    state={'created_at':now(),'status':'RUNNING','test_kind':'MIXED_SYNTHETIC_504_REAL_DEEPSEEK',
        'preferred_model':'gpt6','real_http_limit':1,'real_http_requests':0,
        'synthetic_http_responses':0,'requests':[],'records':[],
        'gpt_network_call':'NOT_RUN_LOCAL_504_INJECTION','task_database_modified':False,
        'windows_compile':'NOT_RUN','teacher_review':'NOT_RUN'}
    def save():write_json(output/'result.json',state)
    class MixedTransport(httpx.AsyncBaseTransport):
        def __init__(self):self.real=httpx.AsyncHTTPTransport(retries=0)
        async def handle_async_request(self,request):
            model=json.loads(request.content)['model']
            if model==settings.model and state['synthetic_http_responses']==0:
                state['synthetic_http_responses']+=1;save()
                return httpx.Response(504,request=request,json={'error':'LOCAL_SYNTHETIC_TIMEOUT_FOR_TEST'})
            if model!='deepseek-flash' or state['real_http_requests']>=state['real_http_limit']:
                raise AgentError('BUDGET_EXHAUSTED','Mixed validation permits only one real Flash request')
            state['real_http_requests']+=1;save()
            return await self.real.handle_async_request(request)
        async def aclose(self):await self.real.aclose()
    def before(metadata):
        if len(state['requests'])>=2:
            raise AgentError('BUDGET_EXHAUSTED','Mixed validation permits only two counted attempts')
        state['requests'].append(metadata);save()
    def record(metadata):state['records'].append(metadata);save()
    save()
    try:
        provider=CompatibleChatProvider(settings,preferred_model='gpt6',transport=MixedTransport(),
            before_request=before,record=record)
        response=provider.check()
        state['response']=response
        state['actual_response']=provider.last_response_metadata
        ids=[row['model_id'] for row in state['requests']]
        passed=bool(response.strip()) and ids==['gpt6','deepseek-flash'] and state['real_http_requests']==1
        state['status']='PASS' if passed else 'FAIL'
    except AgentError as exc:
        state.update(status='FAIL',error={'code':exc.code,'message':exc.message})
    finally:
        state['finished_at']=now();save()
    print(json.dumps({'status':state['status'],'test_kind':state['test_kind'],
        'real_http_requests':state['real_http_requests'],'synthetic_http_responses':state['synthetic_http_responses'],
        'actual_model':state.get('actual_response',{}).get('model_id'),'report':str(output/'result.json')},ensure_ascii=True))
    return 0 if state['status']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())
