"""MockTransport only: delivery failures route, completed mathematical verdicts do not."""
import hashlib
import json

import httpx
import pytest

from math_agent.domain import MathReview
from math_agent.util import AgentError
from test_model_routing import make_provider, response, VALID
from test_provider_stream import Chunks, event, sse


def streamed(data, content_type='text/event-stream'):
    return httpx.Response(200, headers={'Content-Type': content_type}, stream=Chunks([data]))


@pytest.mark.parametrize('data,content_type,code', [
    (sse([event('', finish='stop')]), 'text/event-stream', 'PROVIDER_EMPTY_RESPONSE'),
    (sse([event('partial')], done=False), 'text/event-stream', 'PROVIDER_STREAM_PROTOCOL'),
    (sse([event('partial', finish='stop')], done=False), 'text/event-stream', 'PROVIDER_STREAM_PROTOCOL'),
    (sse([event('partial')]), 'text/event-stream', 'PROVIDER_STREAM_PROTOCOL'),
    (b'data: {bad}\n\n', 'text/event-stream', 'PROVIDER_STREAM_PROTOCOL'),
    (b'data: {"id":"response-only-no-choices"}\n\n', 'text/event-stream', 'PROVIDER_STREAM_PROTOCOL'),
    (sse([event('first', finish='stop'), event('after-stop')]), 'text/event-stream', 'PROVIDER_STREAM_PROTOCOL'),
    (b'', 'text/event-stream', 'PROVIDER_STREAM_PROTOCOL'),
])
def test_empty_or_broken_sse_discards_partial_body_and_routes_to_flash(tmp_path, data, content_type, code):
    def handler(request):
        return streamed(data, content_type) if request.url.host == 'oneapi.advancedsolver.com' else response(VALID)
    provider, calls, records, _ = make_provider(tmp_path, handler)
    provider.settings.llm_streaming = True
    assert provider.generate('reviewer_math', {}, MathReview)['issues'] == []
    assert [call['model_id'] for call in calls] == ['gpt6', 'deepseek-flash']
    assert provider.last_response_metadata['model_id'] == 'deepseek-flash'
    failure = next(r for r in records if r.get('error_code') == code)
    assert failure['http_status'] == 200 and failure['stream_complete'] is False
    assert failure['billing_uncertain'] is True
    assert len(failure['response_bytes_sha256']) == 64
    if content_type == 'text/event-stream':
        assert failure['response_bytes_sha256'] == hashlib.sha256(data).hexdigest()
        assert failure['received_response_bytes'] == len(data)
    assert not (tmp_path/'invalid').exists()  # no completed schema output or hidden reasoning archived


@pytest.mark.parametrize('finish,refusal,expected', [
    ('length', None, 'OUTPUT_TRUNCATED'), ('content_filter', None, 'PROVIDER_REFUSAL'),
    (None, 'policy refusal', 'PROVIDER_REFUSAL'), ('tool_calls', None, 'PROVIDER_RESPONSE'),
])
def test_explicit_sse_decisions_are_not_misclassified_by_empty_content(tmp_path, finish, refusal, expected):
    provider, calls, records, _ = make_provider(tmp_path,
        lambda request: streamed(sse([event('', finish=finish, refusal=refusal)])))
    provider.settings.llm_streaming = True
    with pytest.raises(AgentError) as error: provider.check()
    assert error.value.code == expected and len(calls) == 1
    assert not any(r.get('event') == 'model_fallback' for r in records)


def test_explicit_sse_error_envelope_does_not_assume_retryable_business_error(tmp_path):
    provider, calls, _, _ = make_provider(tmp_path,
        lambda request: streamed(sse([{'error': {'code': 'policy_or_business_error'}}])))
    provider.settings.llm_streaming = True
    with pytest.raises(AgentError) as error: provider.check()
    assert error.value.code == 'PROVIDER_RESPONSE' and len(calls) == 1


@pytest.mark.parametrize('body', [
    {}, {'error': {'code': 'policy_or_business_error'}},
    {'choices': [{'message': {'content': '', 'refusal': 'explicit refusal'}, 'finish_reason': 'stop'}]},
    {'choices': [{'message': {'content': ''}, 'finish_reason': 'content_filter'}]},
    {'choices': [{'message': {'content': 'partial'}, 'finish_reason': 'length'}]},
    {'choices': [{'message': {'content': VALID}, 'finish_reason': 'stop'}]},
])
def test_non_sse_content_type_does_not_bypass_unknown_or_explicit_business_decision(tmp_path, body):
    provider, calls, records, _ = make_provider(tmp_path, lambda request: httpx.Response(200, json=body))
    provider.settings.llm_streaming = True
    with pytest.raises(AgentError) as error: provider.check()
    assert error.value.code == 'PROVIDER_RESPONSE' and len(calls) == 1
    assert not any(r.get('event') == 'model_fallback' for r in records)


def test_usage_only_chunk_and_ignored_reasoning_do_not_create_false_empty_failure(tmp_path):
    data = sse([{'choices': [], 'usage': {'prompt_tokens': 2}},
        {'choices': [{'index': 0, 'delta': {'reasoning_content': 'PRIVATE_REASONING_SENTINEL'}, 'finish_reason': None}]},
        event(VALID), event(finish='stop')])
    provider, calls, records, _ = make_provider(tmp_path, lambda request: streamed(data))
    provider.settings.llm_streaming = True
    assert provider.generate('reviewer_math', {}, MathReview)['issues'] == []
    assert len(calls) == 1 and 'PRIVATE_REASONING_SENTINEL' not in json.dumps(records)


def test_three_empty_models_exhaust_once_each_with_all_failure_metadata(tmp_path):
    def handler(request):
        return streamed(sse([event('', finish='stop')])) if request.url.host == 'oneapi.advancedsolver.com' else response('   ')
    provider, calls, records, _ = make_provider(tmp_path, handler)
    provider.settings.llm_streaming = True
    with pytest.raises(AgentError) as error: provider.check()
    assert error.value.code == 'PROVIDER_ALL_UNAVAILABLE'
    assert [c['model_id'] for c in calls] == ['gpt6', 'deepseek-flash', 'deepseek-v4-pro']
    failures = [r for r in records if r.get('error_code') == 'PROVIDER_EMPTY_RESPONSE']
    assert len(failures) == 3 and all(r['received_content_chars'] == 0 for r in failures)
    assert all(r['http_status'] == 200 and r['response_bytes_sha256'] for r in failures)
    assert records[-1]['event'] == 'models_exhausted' and provider.last_response_metadata == {}


@pytest.mark.parametrize('content,schema_valid', [
    ('{"issues":[{"severity":"blocking","unit_id":"S01.U01","message":"实际数学错误","evidence":"现有正文"}],"checked_unit_ids":["S01.U01"],"limitations":[]}', True),
    ('{"issues":"invalid business schema"}', False),
])
def test_completed_math_content_is_never_replaced_by_fallback(tmp_path, content, schema_valid):
    provider, calls, records, _ = make_provider(tmp_path,
        lambda request: streamed(sse([event(content), event(finish='stop')])), max_schema_repair_attempts=0)
    provider.settings.llm_streaming = True
    if schema_valid:
        assert provider.generate('reviewer_math', {}, MathReview)['issues'][0]['severity'] == 'blocking'
    else:
        with pytest.raises(AgentError) as error: provider.generate('reviewer_math', {}, MathReview)
        assert error.value.code == 'INVALID_MODEL_JSON'
    assert len(calls) == 1 and not any(r.get('event') == 'model_fallback' for r in records)
