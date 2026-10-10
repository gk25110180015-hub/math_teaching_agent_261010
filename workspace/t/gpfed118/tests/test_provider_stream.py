"""SSE tests use MockTransport only; no live provider calls or real credentials."""
import asyncio
import json
import time

import httpx
from pydantic import SecretStr
import pytest

from math_agent.domain import MathReview
from math_agent.provider import CompatibleChatProvider
from math_agent.settings import Settings
from math_agent.util import AgentError


class Chunks(httpx.AsyncByteStream):
    def __init__(self,chunks):self.chunks=chunks;self.closed=False
    async def __aiter__(self):
        for chunk in self.chunks:yield chunk
    async def aclose(self):self.closed=True


def event(content=None,finish=None,refusal=None):
    delta={}
    if content is not None:delta["content"]=content
    if refusal is not None:delta["refusal"]=refusal
    return {"id":"response-SSE-test","choices":[{"index":0,"delta":delta,"finish_reason":finish}]}


def sse(events,done=True):
    text="".join("data: "+json.dumps(e,ensure_ascii=False)+"\r\n\r\n" for e in events)
    if done:text+="data: [DONE]\r\n\r\n"
    return text.encode("utf-8")


def provider(tmp_path,stream,**settings):
    records=[];calls=[];requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,headers={"Content-Type":"text/event-stream; charset=utf-8"},stream=stream)
    config=Settings(workspace=tmp_path,llm_streaming=True,live_api_enabled=True,api_key=SecretStr("sk-SYNTHETIC_SSE_ONLY_12345"),**settings)
    value=CompatibleChatProvider(config,transport=httpx.MockTransport(handler),record=records.append,before_request=calls.append)
    return value,records,calls,requests


def test_stream_setting_defaults_off_and_env_opt_in(monkeypatch,tmp_path):
    monkeypatch.delenv("MATH_AGENT_LLM_STREAMING",raising=False)
    assert Settings(workspace=tmp_path).llm_streaming is False
    monkeypatch.setenv("MATH_AGENT_LLM_STREAMING","true")
    assert Settings(workspace=tmp_path).llm_streaming is True


def test_sse_utf8_fragments_and_reported_usage_are_preserved(tmp_path):
    data=sse([event("数"),event("学 OK"),event(finish="stop"),{"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10,"api_key":"DO_NOT_LOG"}}])
    stream=Chunks([data[i:i+3] for i in range(0,len(data),3)])
    p,records,calls,requests=provider(tmp_path,stream)
    assert p.check()=="数学 OK"
    assert stream.closed and len(calls)==1
    assert json.loads(requests[0].content)["stream"] is True
    metadata=next(r for r in records if r.get("stream_complete"))
    assert metadata["usage"]=={"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}
    assert metadata["price"] is None and metadata["finish_reason"]=="stop"
    assert metadata["billing_uncertain"] is False
    assert "DO_NOT_LOG" not in str(records) and "SYNTHETIC_SSE" not in str(records)


def test_streamed_json_is_validated_only_after_done(tmp_path):
    data=sse([event('{"issues":[],"checked_unit_ids":'),event('[],"limitations":[]}'),event(finish="stop")])
    p,records,_,_=provider(tmp_path,Chunks([data]))
    assert p.generate("reviewer_math",{"units":[]},MathReview)["issues"]==[]
    metadata=next(r for r in records if r.get("stream_complete"))
    assert metadata["usage"] is None and metadata["billing_uncertain"] is True


@pytest.mark.parametrize("events,done,code",[
    ([event("partial",finish="length")],True,"OUTPUT_TRUNCATED"),
    ([event(refusal="no")],True,"PROVIDER_REFUSAL"),
    ([event("partial",finish="content_filter")],True,"PROVIDER_REFUSAL"),
    ([event("OK",finish="stop")],False,"PROVIDER_STREAM_PROTOCOL"),
    ([event("OK")],True,"PROVIDER_STREAM_PROTOCOL"),
    ([event("",finish="stop")],True,"PROVIDER_EMPTY_RESPONSE"),
    ([event("{}",finish="tool_calls")],True,"PROVIDER_RESPONSE"),
])
def test_stream_never_publishes_partial_refused_or_unfinished_content(tmp_path,events,done,code):
    stream=Chunks([sse(events,done)]);p,records,calls,_=provider(tmp_path,stream)
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code==code
    assert stream.closed and len(calls)==1
    assert not any(r.get("stream_complete") for r in records)


def test_malformed_sse_json_is_not_success(tmp_path):
    p,_,calls,_=provider(tmp_path,Chunks([b'data: {bad}\n\ndata: [DONE]\n\n']))
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code=="PROVIDER_STREAM_PROTOCOL" and len(calls)==1


def test_stream_body_limit_counts_all_event_bytes(tmp_path):
    stream=Chunks([b":"+b" "*(1024*1024)+b"\n\n"]*9)
    p,_,_,_=provider(tmp_path,stream)
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code=="PROVIDER_OVERSIZE" and stream.closed


def test_cancellation_interrupts_a_stalled_stream_and_closes_it(tmp_path):
    state={"active":True}
    class Stalled(Chunks):
        async def __aiter__(self):
            yield sse([event("partial")],False)
            state["active"]=False
            await asyncio.sleep(5)
    stream=Stalled([]);p,_,_,_=provider(tmp_path,stream);p.active=lambda:state["active"]
    start=time.monotonic()
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code=="CANCELLED" and time.monotonic()-start<2
    assert stream.closed


def test_stream_read_timeout_keeps_billing_uncertain_without_body_leak(tmp_path):
    class ReadTimeout(Chunks):
        async def __aiter__(self):
            yield sse([event("partial")],False)
            raise httpx.ReadTimeout("sensitive-provider-body")
    stream=ReadTimeout([]);p,records,_,_=provider(tmp_path,stream)
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code=="PROVIDER_TIMEOUT" and stream.closed
    assert records[-1]["billing_uncertain"] is True
    assert "sensitive-provider-body" not in str(records)+str(error.value)


def test_stream_total_deadline_terminates_stalled_read(tmp_path):
    class Stalled(Chunks):
        async def __aiter__(self):
            yield sse([event("partial")],False)
            await asyncio.sleep(5)
    stream=Stalled([]);p,records,_,_=provider(tmp_path,stream,llm_total_timeout_seconds=0.08)
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code=="PROVIDER_TOTAL_TIMEOUT" and stream.closed
    assert any(r.get("billing_uncertain") for r in records)


def test_stream_http_retry_budget_is_unchanged(tmp_path):
    p,_,calls,_=provider(tmp_path,Chunks([]))
    def handler(request):return httpx.Response(429,headers={"Retry-After":"0"})
    p.transport=httpx.MockTransport(handler)
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code=="PROVIDER_RATE_LIMIT" and len(calls)==3


def test_sse_comments_fields_and_multiline_data_are_supported(tmp_path):
    data=(b': heartbeat\nevent: message\nid: 1\n'
          b'data: {"choices":\n'
          b'data: [{"index":0,"delta":{"role":"assistant","content":"OK"},"finish_reason":"stop"}]}\n\n'
          b'data: [DONE]\n\n')
    p,records,_,_=provider(tmp_path,Chunks([data]))
    assert p.check()=="OK" and records[-1]["stream_complete"]


def test_sse_content_after_finish_is_rejected(tmp_path):
    p,records,_,_=provider(tmp_path,Chunks([sse([event("OK",finish="stop"),event("more")])]))
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code=="PROVIDER_STREAM_PROTOCOL"
    assert not records[-1]["stream_complete"]


def test_stream_requires_sse_content_type_even_for_valid_json(tmp_path):
    p,records,_,_=provider(tmp_path,Chunks([]))
    p.transport=httpx.MockTransport(lambda request:httpx.Response(200,json={"choices":[{"message":{"content":"OK"},"finish_reason":"stop"}]}))
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code=="PROVIDER_RESPONSE" and not records[-1]["stream_complete"]


def test_cancel_as_headers_arrive_still_closes_response(tmp_path):
    state={"active":True};stream=Chunks([sse([event("OK",finish="stop")])])
    p,records,_,_=provider(tmp_path,stream);p.active=lambda:state["active"]
    def handler(request):
        state["active"]=False
        return httpx.Response(200,headers={"Content-Type":"text/event-stream"},stream=stream)
    p.transport=httpx.MockTransport(handler)
    with pytest.raises(AgentError) as error:p.check()
    assert error.value.code=="CANCELLED" and stream.closed
    assert not any(r.get("stream_complete") for r in records)


@pytest.mark.parametrize("streaming",[True,False])
def test_elapsed_seconds_includes_delayed_response_body(tmp_path,streaming):
    class Delayed(Chunks):
        async def __aiter__(self):
            await asyncio.sleep(0.05)
            if streaming:
                yield sse([event("OK",finish="stop")])
            else:
                yield json.dumps({"choices":[{"message":{"content":"OK"},"finish_reason":"stop"}]}).encode()
    stream=Delayed([]);p,records,_,_=provider(tmp_path,stream)
    p.settings.llm_streaming=streaming
    p.transport=httpx.MockTransport(lambda request:httpx.Response(200,
        headers={"Content-Type":"text/event-stream" if streaming else "application/json"},stream=stream))
    assert p.check()=="OK" and stream.closed
    headers=next(r for r in records if "headers_elapsed_seconds" in r)
    total=next(r for r in records if "elapsed_seconds" in r)
    assert total["elapsed_seconds"]>=0.045
    assert total["elapsed_seconds"]-headers["headers_elapsed_seconds"]>=0.04
    assert total["price"] is None and total["billing_uncertain"] is True
