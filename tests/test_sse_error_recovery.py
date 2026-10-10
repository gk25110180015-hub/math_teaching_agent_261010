"""Provider control failures vs completed model decisions, using MockTransport."""
import json
from pathlib import Path

import httpx
import pytest

from math_agent.domain import MathReview
from math_agent.util import AgentError, digest
from test_model_routing import make_provider, response, VALID
from test_provider_stream import sse, event
from test_provider_transport_recovery import streamed


@pytest.mark.parametrize('error', [
    {'code':'server_error','message':'upstream interrupted'},
    {'type':'rate_limit_error','message':'capacity exhausted'},
    {'code':'invalid_api_key','message':'this provider cannot serve'},
    {'message':'unknown upstream API failure'},
    {'code':'model_not_found'}, 'provider unavailable',
])
def test_sse_control_error_routes_to_flash_and_keeps_sanitized_diagnostics(tmp_path,error):
    data=sse([event('DISCARD_PARTIAL_BODY'),{'error':error}])
    def handler(request):
        return streamed(data) if request.url.host=='oneapi.advancedsolver.com' else response(VALID)
    provider,calls,records,_=make_provider(tmp_path,handler)
    provider.settings.llm_streaming=True
    result=provider.generate('reviewer_math',{},MathReview)
    assert result['issues']==[] and [c['model_id'] for c in calls]==['gpt6','deepseek-flash']
    failed=next(r for r in records if r.get('error_code')=='PROVIDER_STREAM_ERROR')
    assert failed['http_status']==200 and failed['stream_complete'] is False
    assert failed['response_bytes_sha256']==digest(data) and failed['billing_uncertain'] is True
    archive=Path(failed['invalid_response_archive']).read_bytes()
    assert digest(archive)==failed['archive_sha256'] and 'provider_error' in json.loads(archive)
    assert b'DISCARD_PARTIAL_BODY' not in archive
    assert provider.last_response_metadata['model_id']=='deepseek-flash'


@pytest.mark.parametrize('code', ['policy_violation','content_filter','moderation_blocked','safety_error',
    'refusal','invalid_request_error','invalid_parameter','context_length_exceeded',
    'unsupported_parameter','bad_request'])
def test_explicit_content_or_request_parameter_rejections_remain_blocked(tmp_path,code):
    provider,calls,records,_=make_provider(tmp_path,lambda request:streamed(sse([{'error':{'code':code}}])))
    provider.settings.llm_streaming=True
    with pytest.raises(AgentError) as error:provider.check()
    assert error.value.code=='PROVIDER_RESPONSE' and len(calls)==1
    assert not any(r.get('event')=='model_fallback' for r in records)
    assert next(r for r in records if r.get('invalid_response_archive'))['archive_redacted']


def test_failure_archive_excludes_hidden_fields_and_both_actual_configured_keys(tmp_path):
    body={'error':{'code':'server_error','message':'synthetic-gpt-secret synthetic-deepseek-secret',
        'reasoning_content':'PRIVATE_REASONING_SENTINEL','internal':{'token':'PRIVATE_NESTED_SENTINEL'}},
        'reasoning_content':'PRIVATE_TOP_SENTINEL'}
    provider,calls,records,_=make_provider(tmp_path,lambda request:streamed(sse([body]))
        if request.url.host=='oneapi.advancedsolver.com' else response('OK'))
    provider.settings.llm_streaming=True
    assert provider.check()=='OK'
    combined=json.dumps(records)+''.join(p.read_text(encoding='utf-8') for p in (tmp_path/'invalid').iterdir())
    for private in ('synthetic-gpt-secret','synthetic-deepseek-secret','PRIVATE_REASONING_SENTINEL',
                    'PRIVATE_NESTED_SENTINEL','PRIVATE_TOP_SENTINEL'):
        assert private not in combined


def test_stream_error_then_flash_timeout_uses_pro_and_keeps_each_attempt(tmp_path):
    def handler(request):
        model=json.loads(request.content)['model']
        if model=='gpt-6-astra':return streamed(sse([{'error':{'code':'server_error'}}]))
        if model=='deepseek-flash':raise httpx.ReadTimeout('synthetic timeout')
        return response('OK',model='deepseek-v4-pro')
    provider,calls,records,_=make_provider(tmp_path,handler)
    provider.settings.llm_streaming=True
    assert provider.check()=='OK'
    assert [c['model_id'] for c in calls]==['gpt6','deepseek-flash','deepseek-v4-pro']
    assert len({c['call_id'] for c in calls})==3


def test_no_fallback_flag_keeps_the_same_failed_attempt(tmp_path):
    provider,calls,records,_=make_provider(tmp_path,lambda request:streamed(sse([{'error':{'code':'server_error'}}])),fallback=False)
    provider.settings.llm_streaming=True
    with pytest.raises(AgentError) as error:provider.check()
    assert error.value.code=='PROVIDER_STREAM_ERROR' and len(calls)==1


def test_budget_failure_before_fallback_is_never_hidden(tmp_path):
    provider,calls,records,_=make_provider(tmp_path,lambda request:streamed(sse([{'error':{'code':'server_error'}}])))
    provider.settings.llm_streaming=True
    original=provider.before_request
    def reserve(metadata):
        if metadata['model_id']!='gpt6':raise AgentError('BUDGET_EXHAUSTED','synthetic budget gate')
        original(metadata)
    provider.before_request=reserve
    with pytest.raises(AgentError) as error:provider.check()
    assert error.value.code=='BUDGET_EXHAUSTED' and len(calls)==1
