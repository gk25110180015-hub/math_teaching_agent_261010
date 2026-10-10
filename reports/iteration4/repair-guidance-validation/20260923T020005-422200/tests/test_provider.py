import json
import httpx
import pytest
from pydantic import SecretStr
from math_agent.domain import MathReview
from math_agent.provider import CompatibleChatProvider, extract_json
from math_agent.settings import Settings
from math_agent.util import AgentError, scrub


def provider(tmp_path,handler,**settings):
    records=[];calls=[]
    s=Settings(workspace=tmp_path,live_api_enabled=True,api_key=SecretStr('sk-SYNTHETIC_TEST_ONLY_123456'),**settings)
    p=CompatibleChatProvider(s,transport=httpx.MockTransport(handler),record=records.append,before_request=calls.append)
    return p,records,calls


def response(content,finish='stop'):
    return httpx.Response(200,json={'choices':[{'message':{'content':content},'finish_reason':finish}]})


def test_T18_invalid_json_bounded(tmp_path):
    p,records,calls=provider(tmp_path,lambda request:response('{"issues":'))
    with pytest.raises(AgentError,match='结构修复预算'):
        p.generate('reviewer_math',{'units':[]},MathReview)
    assert len(calls)==3
    assert all('Bearer' not in json.dumps(r) for r in records)


def test_T18_truncated_not_repaired_as_success(tmp_path):
    p,_,calls=provider(tmp_path,lambda request:response('{"issues":[]}',finish='length'))
    with pytest.raises(AgentError) as exc:p.generate('reviewer_math',{},MathReview)
    assert exc.value.code=='OUTPUT_TRUNCATED'
    assert len(calls)==1


def test_T19_auth_no_retry_or_body_leak(tmp_path):
    p,records,calls=provider(tmp_path,lambda request:httpx.Response(401,text='Bearer sk-SYNTHETIC_TEST_ONLY_123456'))
    with pytest.raises(AgentError) as exc:p.check()
    assert exc.value.code=='PROVIDER_AUTH'
    assert len(calls)==1
    assert 'SYNTHETIC' not in str(records)+str(exc.value)


def test_T19_429_budget_retries(tmp_path):
    p,records,calls=provider(tmp_path,lambda request:httpx.Response(429,headers={'Retry-After':'0'}))
    with pytest.raises(AgentError) as exc:p.check()
    assert exc.value.code=='PROVIDER_RATE_LIMIT'
    assert len(calls)==3


def test_T19_timeout_classified(tmp_path):
    def handler(request): raise httpx.ReadTimeout('sensitive server text',request=request)
    p,records,calls=provider(tmp_path,handler)
    with pytest.raises(AgentError) as exc:p.check()
    assert exc.value.code=='PROVIDER_TIMEOUT'
    assert 'sensitive' not in str(exc.value)
    assert records[-1]['billing_uncertain']


def test_T20_minimal_protocol_and_exact_url(tmp_path):
    seen=[]
    def handler(request):
        seen.append(request)
        return response('{"issues":[],"checked_unit_ids":[],"limitations":[]}')
    p,records,calls=provider(tmp_path,handler)
    p.generate('reviewer_math',{},MathReview)
    assert str(seen[0].url)=='https://oneapi.advancedsolver.com/v1/chat/completions'
    assert set(json.loads(seen[0].content))=={'model','messages','temperature'}
    assert any(r.get('usage','notfound') is None for r in records)


def test_T55_scrub(monkeypatch):
    monkeypatch.setenv('MATH_AGENT_API_KEY','custom-secret-value')
    value=scrub('Authorization: Bearer sk-FAKE_FOR_TESTS_12345 custom-secret-value')
    assert 'custom-secret-value' not in value and 'FAKE_FOR_TESTS' not in value


def test_supplier_usage_cannot_echo_secret_into_logs(tmp_path):
    def handler(request):
        return httpx.Response(200,json={'choices':[{'message':{'content':'OK'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':2,'total_tokens':'sk-DO_NOT_LOG_SENTINEL','api_key':'sk-DO_NOT_LOG_SENTINEL'}})
    p,records,_=provider(tmp_path,handler)
    assert p.check()=='OK'
    assert records[-1]['usage']=={'prompt_tokens':2}
    assert 'DO_NOT_LOG' not in str(records)


def test_json_reject_multiple_objects():
    with pytest.raises(ValueError):extract_json('{} {}')


@pytest.mark.real_api
def test_live_provider_opt_in(tmp_path):
    s=Settings(workspace=tmp_path)
    if not s.live_api_enabled or not s.api_key.get_secret_value():
        pytest.skip('NOT_RUN: fresh environment key/live opt-in missing')
    assert CompatibleChatProvider(s).check().strip()
