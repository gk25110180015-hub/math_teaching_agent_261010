"""Offline transport tests for prompt provenance, including failed requests."""
import json

import httpx
import pytest
from pydantic import SecretStr

from math_agent.benchmark import request_metrics
from math_agent.domain import MathReview
from math_agent.provider import CompatibleChatProvider
from math_agent.settings import Settings
from math_agent.util import AgentError, digest


def make_provider(tmp_path, handler, **overrides):
    settings = Settings(workspace=tmp_path, live_api_enabled=True, llm_streaming=False,
                        api_key=SecretStr('sk-SYNTHETIC_PROMPT_METADATA_ONLY'),
                        max_network_retries=0, **overrides)
    calls, records = [], []
    client = CompatibleChatProvider(settings, transport=httpx.MockTransport(handler),
                                    before_request=calls.append, record=records.append)
    return client, calls, records


@pytest.mark.parametrize('outcome', ['valid', 'invalid_json', 'http_504'])
def test_prompt_identity_recorded_before_send_and_on_failures(tmp_path, monkeypatch, outcome):
    from math_agent import provider
    instruction = '版本 9。测试提示词。'
    (tmp_path/'reviewer_math.md').write_text(instruction, encoding='utf-8')
    monkeypatch.setattr(provider, 'PROMPTS', tmp_path)
    def handler(request):
        assert instruction in json.loads(request.content)['messages'][0]['content']
        if outcome == 'http_504':
            return httpx.Response(504)
        text = '{"issues":[],"checked_unit_ids":[],"limitations":[]}' if outcome == 'valid' else '{'
        return httpx.Response(200, json={'choices':[{'message':{'content':text},'finish_reason':'stop'}]})
    client, calls, records = make_provider(tmp_path, handler, max_schema_repair_attempts=0)
    if outcome == 'valid':
        client.generate('reviewer_math', {}, MathReview)
    else:
        with pytest.raises(AgentError):
            client.generate('reviewer_math', {}, MathReview)
    assert len(calls) == 1
    for item in calls + records:
        assert item['prompt_version'] == 9
        assert item['prompt_version_source'] == 'declared_prompt_header'
        assert item['prompt_hash'] == digest(instruction)
        assert item['schema_hash'] == digest(MathReview.model_json_schema())
    assert 'sk-SYNTHETIC_PROMPT_METADATA_ONLY' not in json.dumps(calls + records)


def test_schema_retry_keeps_the_actual_loaded_prompt_identity(tmp_path, monkeypatch):
    from math_agent import provider
    path = tmp_path/'reviewer_math.md'
    path.write_text('版本1。初始提示词。', encoding='utf-8')
    monkeypatch.setattr(provider, 'PROMPTS', tmp_path)
    attempts = []
    def handler(request):
        attempts.append(json.loads(request.content))
        path.write_text('版本2。运行中落盘的新提示词。', encoding='utf-8')
        text = '{' if len(attempts) == 1 else '{"issues":[],"checked_unit_ids":[],"limitations":[]}'
        return httpx.Response(200, json={'choices':[{'message':{'content':text},'finish_reason':'stop'}]})
    client, calls, records = make_provider(tmp_path, handler, max_schema_repair_attempts=1)
    client.generate('reviewer_math', {}, MathReview)
    assert len(calls) == 2
    assert all(item['prompt_version'] == 1 for item in calls + records)
    assert all(item['prompt_hash'] == digest('版本1。初始提示词。') for item in calls + records)
    assert all('初始提示词' in item['messages'][0]['content'] for item in attempts)


def test_undeclared_version_is_not_invented(tmp_path, monkeypatch):
    from math_agent import provider
    (tmp_path/'reviewer_math.md').write_text('没有版本头。', encoding='utf-8')
    monkeypatch.setattr(provider, 'PROMPTS', tmp_path)
    client, calls, _ = make_provider(tmp_path, lambda request:httpx.Response(504))
    with pytest.raises(AgentError):
        client.generate('reviewer_math', {}, MathReview)
    assert calls[0]['prompt_version'] is None
    assert calls[0]['prompt_version_source'] == 'UNDECLARED'


def test_metrics_distinguish_real_headers_legacy_hardcoding_and_missing_provenance():
    events = [
        {'sequence':1,'type':'provider.request','payload':{'role':'reviewer','prompt_version':3,
            'prompt_version_source':'declared_prompt_header','prompt_hash':'actual','schema_hash':'schema'}},
        {'sequence':2,'type':'provider.result','payload':{'role':'reviewer','status':'HTTP_504'}},
        {'sequence':3,'type':'provider.request','payload':{'role':'reviewer'}},
        {'sequence':4,'type':'provider.result','payload':{'role':'reviewer','prompt_version':1,'prompt_hash':'legacy','output_hash':'output'}},
        {'sequence':5,'type':'provider.request','payload':{'role':'writer'}},
    ]
    records = request_metrics(events, 3, 60)['requests']
    assert (records[0]['prompt_version'], records[0]['prompt_version_source']) == (3, 'declared_prompt_header')
    assert records[0]['prompt_hash'] == 'actual' and records[0]['schema_hash'] == 'schema'
    assert records[1]['prompt_hash'] == 'legacy'
    assert records[1]['prompt_version_source'] == 'LEGACY_HARDCODED_NOT_VERIFIED'
    assert records[2]['prompt_version'] is None and records[2]['prompt_hash'] is None
    assert records[2]['prompt_version_source'] == 'UNKNOWN_NOT_RECORDED'
