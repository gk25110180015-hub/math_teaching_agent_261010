"""Offline transports only: bounded routing, provenance and secret isolation."""
import json

import httpx
import pytest
from pydantic import SecretStr

from math_agent.domain import MathReview
from math_agent.provider import CompatibleChatProvider, invalid_json_escape_diagnostics
from math_agent.settings import Settings
from math_agent.util import AgentError, scrub


VALID = '{"issues":[],"checked_unit_ids":[],"limitations":[]}'
MODEL_IDS = ['gpt6', 'deepseek-flash', 'deepseek-v4-pro']


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setenv('MATH_AGENT_API_KEY', '')
    monkeypatch.setenv('MATH_AGENT_DEEPSEEK_API_KEY', '')
    monkeypatch.setenv('MATH_AGENT_LLM_STREAMING', 'false')


def response(content='OK', **body):
    return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}], **body})


def make_provider(tmp_path, handler, *, preferred='gpt6', fallback=True, **settings):
    calls, records, sent = [], [], []
    async def tracked(request):
        sent.append(request)
        value = handler(request)
        if hasattr(value, '__await__'):
            return await value
        return value
    config = Settings(workspace=tmp_path, live_api_enabled=True, llm_streaming=False,
        api_key=SecretStr('synthetic-gpt-secret'), deepseek_api_key=SecretStr('synthetic-deepseek-secret'),
        **settings)
    provider = CompatibleChatProvider(config, transport=httpx.MockTransport(tracked),
        before_request=calls.append, record=records.append, preferred_model=preferred,
        allow_fallback=fallback, failure_dir=tmp_path/'invalid')
    return provider, calls, records, sent


def test_public_profiles_default_env_only_and_no_secret(tmp_path, monkeypatch):
    monkeypatch.setenv('MATH_AGENT_DEEPSEEK_API_KEY', 'private-custom-format-key')
    settings = Settings(workspace=tmp_path, live_api_enabled=True)
    public = settings.public()
    assert public['default_model_id'] == 'gpt6'
    assert public['fallback_order'] == MODEL_IDS
    assert [profile['id'] for profile in public['models']] == MODEL_IDS
    assert not public['models'][0]['configured']
    assert all(profile['configured'] for profile in public['models'][1:])
    assert 'private-custom-format-key' not in json.dumps(public)
    assert settings.model_secret('deepseek-flash').get_secret_value() == 'private-custom-format-key'
    assert settings.model_profile('deepseek-flash')['base_url'] == 'https://api.deepseek.com'
    with pytest.raises(ValueError):
        settings.model_profile('invented-model')


@pytest.mark.parametrize('status', [408, 429, 500, 502, 503, 504, 401, 403, 404])
def test_failure_switches_immediately_with_request_identity(tmp_path, status):
    def handler(request):
        return httpx.Response(status) if request.url.host == 'oneapi.advancedsolver.com' else response(model='deepseek-flash')
    provider, calls, records, sent = make_provider(tmp_path, handler)
    assert provider.check() == 'OK'
    assert [call['model_id'] for call in calls] == ['gpt6', 'deepseek-flash']
    assert len({call['call_id'] for call in calls}) == 2
    routing = [record for record in records if record.get('event') == 'model_fallback']
    assert len(routing) == 1 and routing[0]['from_model_id'] == 'gpt6'
    assert routing[0]['to_model_id'] == 'deepseek-flash'
    assert routing[0]['call_id'] == calls[0]['call_id']
    assert provider.last_response_metadata['model_id'] == 'deepseek-flash'
    assert provider.last_response_metadata['reported_model'] == 'deepseek-flash'
    assert str(sent[1].url) == 'https://api.deepseek.com/chat/completions'
    assert sent[0].headers['authorization'] == 'Bearer synthetic-gpt-secret'
    assert sent[1].headers['authorization'] == 'Bearer synthetic-deepseek-secret'


@pytest.mark.parametrize('preferred, expected', [
    ('gpt6', MODEL_IDS),
    ('deepseek-flash', ['deepseek-flash', 'gpt6', 'deepseek-v4-pro']),
    ('deepseek-v4-pro', ['deepseek-v4-pro', 'gpt6', 'deepseek-flash']),
])
def test_all_unavailable_is_bounded_and_ordered(tmp_path, preferred, expected):
    provider, calls, records, _ = make_provider(tmp_path, lambda request: httpx.Response(504), preferred=preferred)
    with pytest.raises(AgentError) as error:
        provider.check()
    assert error.value.code == 'PROVIDER_ALL_UNAVAILABLE'
    assert [call['model_id'] for call in calls] == expected
    assert all(call['preferred_model_id'] == preferred for call in calls)
    assert len([record for record in records if record.get('transport_status') == 'FAILED']) == 3
    assert records[-1]['event'] == 'models_exhausted'
    assert provider.last_response_metadata == {}


def test_deepseek_exact_payload_ignores_reasoning_and_never_logs_keys(tmp_path):
    def handler(request):
        return httpx.Response(200, json={'model': 'deepseek-v4-pro',
            'id': 'synthetic-deepseek-secret',
            'choices': [{'finish_reason': 'stop', 'message': {'content': VALID,
                'reasoning_content': 'PRIVATE_REASONING_SENTINEL synthetic-gpt-secret synthetic-deepseek-secret'}}]})
    provider, calls, records, sent = make_provider(tmp_path, handler, preferred='deepseek-v4-pro')
    assert provider.generate('reviewer_math', {}, MathReview)['issues'] == []
    payload = json.loads(sent[0].content)
    assert set(payload) == {'model', 'messages', 'thinking', 'reasoning_effort', 'stream'}
    assert payload['thinking'] == {'type': 'enabled'} and payload['reasoning_effort'] == 'high'
    assert payload['stream'] is False and payload['model'] == 'deepseek-v4-pro'
    logged = json.dumps(calls + records) + json.dumps(provider.last_response_metadata)
    assert 'PRIVATE_REASONING_SENTINEL' not in logged
    assert 'synthetic-gpt-secret' not in logged and 'synthetic-deepseek-secret' not in logged
    assert records[-1]['call_id'] == calls[-1]['call_id']


def test_schema_repair_stays_on_fallback_then_next_call_prefers_gpt(tmp_path):
    seen = []
    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        if len(seen) == 1:
            return httpx.Response(504)
        return response('{' if len(seen) == 2 else VALID)
    provider, calls, records, _ = make_provider(tmp_path, handler)
    assert provider.generate('reviewer_math', {}, MathReview)['issues'] == []
    assert [call['model_id'] for call in calls] == ['gpt6', 'deepseek-flash', 'deepseek-flash']
    assert records[-1]['call_id'] == calls[-1]['call_id']
    assert provider.generate('reviewer_math', {}, MathReview)['issues'] == []
    assert calls[-1]['model_id'] == 'gpt6'
    assert provider.preferred_model == 'gpt6'


def test_invalid_schema_never_switches_models(tmp_path):
    provider, calls, records, _ = make_provider(tmp_path, lambda request: response('{'), preferred='deepseek-flash')
    with pytest.raises(AgentError) as error:
        provider.generate('reviewer_math', {}, MathReview)
    assert error.value.code == 'INVALID_MODEL_JSON'
    assert [call['model_id'] for call in calls] == ['deepseek-flash'] * 3
    assert not any(record.get('event') for record in records)


def test_schema_repair_transport_failure_does_not_switch_its_author(tmp_path):
    attempts = []
    def handler(request):
        attempts.append(json.loads(request.content)['model'])
        if len(attempts) == 1:
            return httpx.Response(504)
        if len(attempts) == 2:
            return response('{')
        return httpx.Response(504, headers={'Retry-After': '0'})
    provider, calls, _, _ = make_provider(tmp_path, handler)
    with pytest.raises(AgentError) as error:
        provider.generate('reviewer_math', {}, MathReview)
    assert error.value.code == 'PROVIDER_UNAVAILABLE'
    assert [call['model_id'] for call in calls] == ['gpt6'] + ['deepseek-flash'] * 4


def test_partial_sse_timeout_is_discarded_before_nonstream_fallback(tmp_path):
    closed = []
    class PartialStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"index":0,"delta":{"content":"UNPUBLISHED_PARTIAL_SENTINEL"}}]}\n\n'
            raise httpx.ReadTimeout('stream stalled')
        async def aclose(self):
            closed.append(True)
    def handler(request):
        if request.url.host == 'oneapi.advancedsolver.com':
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=PartialStream())
        return response('COMPLETE_FALLBACK_CONTENT')
    provider, calls, records, sent = make_provider(tmp_path, handler)
    provider.settings.llm_streaming = True
    assert provider.check() == 'COMPLETE_FALLBACK_CONTENT'
    assert closed and [call['model_id'] for call in calls] == ['gpt6', 'deepseek-flash']
    assert 'UNPUBLISHED_PARTIAL_SENTINEL' not in json.dumps(records)
    assert 'UNPUBLISHED_PARTIAL_SENTINEL' not in sent[1].content.decode()
    first = next(record for record in records if record.get('error_code') == 'PROVIDER_TIMEOUT')
    assert first['stream_complete'] is False and first['billing_uncertain'] is True
    assert not (tmp_path/'invalid').exists()


@pytest.mark.parametrize('status, expected_code', [(400, 'PROVIDER_HTTP'), (422, 'PROVIDER_HTTP')])
def test_business_parameter_errors_do_not_silently_drop_parameters(tmp_path, status, expected_code):
    provider, calls, _, _ = make_provider(tmp_path, lambda request: httpx.Response(status))
    with pytest.raises(AgentError) as error:
        provider.check()
    assert error.value.code == expected_code and len(calls) == 1


@pytest.mark.parametrize('finish, code', [('length', 'OUTPUT_TRUNCATED'), ('content_filter', 'PROVIDER_REFUSAL')])
def test_truncation_refusal_never_falls_back(tmp_path, finish, code):
    provider, calls, _, _ = make_provider(tmp_path, lambda request: httpx.Response(200,
        json={'choices': [{'message': {'content': '{'}, 'finish_reason': finish}]}))
    with pytest.raises(AgentError) as error:
        provider.check()
    assert error.value.code == code and len(calls) == 1


def test_request_budget_checked_again_before_fallback_send(tmp_path):
    provider, calls, records, sent = make_provider(tmp_path, lambda request: httpx.Response(504))
    def counted(metadata):
        if calls:
            raise AgentError('BUDGET_EXHAUSTED', 'request budget')
        calls.append(metadata)
    provider.before_request = counted
    with pytest.raises(AgentError) as error:
        provider.check()
    assert error.value.code == 'BUDGET_EXHAUSTED'
    assert len(sent) == len(calls) == 1


def test_cancellation_after_failure_never_sends_alternative(tmp_path):
    active = [True]
    def handler(request):
        active[0] = False
        return httpx.Response(504)
    provider, calls, _, sent = make_provider(tmp_path, handler)
    provider.active = lambda: active[0]
    with pytest.raises(AgentError) as error:
        provider.check()
    assert error.value.code == 'CANCELLED' and len(calls) == len(sent) == 1


@pytest.mark.parametrize('exception', [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError])
def test_network_and_timeouts_fall_back(tmp_path, exception):
    def handler(request):
        if request.url.host == 'oneapi.advancedsolver.com':
            raise exception('do not log sensitive server text', request=request)
        return response()
    provider, calls, records, _ = make_provider(tmp_path, handler)
    assert provider.check() == 'OK'
    assert [call['model_id'] for call in calls] == ['gpt6', 'deepseek-flash']
    assert 'sensitive server text' not in json.dumps(records)


def test_total_deadline_falls_back_without_reusing_stalled_request(tmp_path):
    import asyncio
    cancelled = []
    async def handler(request):
        if request.url.host == 'oneapi.advancedsolver.com':
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append('gpt6')
                raise
        return response()
    # An actual deadline still cancels the indefinitely stalled request. Allow
    # normal Windows scheduling latency for the healthy fallback: 30 ms was
    # shorter than a scheduler delay during the full TeX compilation suite.
    provider, calls, records, _ = make_provider(tmp_path, handler, llm_total_timeout_seconds=2.0)
    assert provider.check() == 'OK'
    assert cancelled == ['gpt6']
    assert [call['model_id'] for call in calls] == ['gpt6', 'deepseek-flash']
    failures = [record for record in records if record.get('error_code') == 'PROVIDER_TOTAL_TIMEOUT']
    assert len(failures) == 1 and failures[0]['model_id'] == 'gpt6'
    assert provider.last_response_metadata['model_id'] == 'deepseek-flash'
    assert provider.last_response_metadata['transport_status'] == 'SUCCESS'


def test_explicit_no_fallback_keeps_original_retry_limit(tmp_path):
    provider, calls, records, _ = make_provider(tmp_path,
        lambda request: httpx.Response(504, headers={'Retry-After': '0'}), fallback=False)
    with pytest.raises(AgentError) as error:
        provider.check()
    assert error.value.code == 'PROVIDER_UNAVAILABLE'
    assert [call['model_id'] for call in calls] == ['gpt6'] * 3
    assert not any(record.get('event') for record in records)


def test_unconfigured_preferred_skips_without_a_charged_request(tmp_path):
    provider, calls, records, _ = make_provider(tmp_path, lambda request: response())
    provider.settings.api_key = SecretStr('')
    assert provider.check() == 'OK'
    assert calls[0]['model_id'] == 'deepseek-flash' and len(calls) == 1
    assert records[0]['code'] == 'PROVIDER_NOT_CONFIGURED'
    provider.allow_fallback = False
    with pytest.raises(AgentError) as error:
        provider.check()
    assert error.value.code == 'PROVIDER_NOT_CONFIGURED' and len(calls) == 1


def test_both_keys_redacted_before_diagnostics_archive_and_schema_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv('MATH_AGENT_DEEPSEEK_API_KEY', 'environment-only-deepseek-secret')
    payload = r'{"issues":"\q synthetic-gpt-secret synthetic-deepseek-secret environment-only-deepseek-secret"}'
    provider, _, records, sent = make_provider(tmp_path, lambda request: response(payload), preferred='deepseek-flash')
    with pytest.raises(AgentError):
        provider.generate('reviewer_math', {}, MathReview)
    evidence = json.dumps(records) + ''.join(path.read_text(encoding='utf-8') for path in (tmp_path/'invalid').iterdir())
    evidence += ''.join(request.content.decode() for request in sent[1:])
    assert 'synthetic-gpt-secret' not in evidence
    assert 'synthetic-deepseek-secret' not in evidence
    assert 'environment-only-deepseek-secret' not in evidence
    assert 'environment-only-deepseek-secret' not in scrub('environment-only-deepseek-secret')
    diagnostic = invalid_json_escape_diagnostics(payload, secrets=('synthetic-gpt-secret', 'synthetic-deepseek-secret'))
    assert 'synthetic-gpt-secret' not in json.dumps(diagnostic)
