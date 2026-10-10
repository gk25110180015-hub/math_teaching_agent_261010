import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from math_agent.domain import MathReview
from math_agent.provider import CompatibleChatProvider
from math_agent.settings import Settings
from math_agent.util import AgentError, digest


def test_invalid_json_archived_separately_without_environment_secret(tmp_path, monkeypatch):
    monkeypatch.delenv('MATH_AGENT_API_KEY', raising=False)
    secret = 'synthetic-custom-format-credential'
    response = '{"issues": "sentinel mathematical draft ' + secret
    records = []
    provider = CompatibleChatProvider(
        Settings(workspace=tmp_path, live_api_enabled=True, api_key=SecretStr(secret),
                 max_schema_repair_attempts=1, llm_streaming=False),
        record=records.append, failure_dir=tmp_path/'failures',
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={
            'choices': [{'message': {'content': response}, 'finish_reason': 'stop'}]})))
    with pytest.raises(AgentError) as error:
        provider.generate('reviewer_math', {}, MathReview)
    assert error.value.code == 'INVALID_MODEL_JSON'
    archives = [r for r in records if 'archive_sha256' in r]
    assert len(archives) == 2
    assert len({r['invalid_response_archive'] for r in archives}) == 2
    for record in archives:
        path = Path(record['invalid_response_archive'])
        payload = path.read_bytes()
        assert b'sentinel mathematical draft' in payload and b'[REDACTED]' in payload
        assert secret.encode() not in payload
        assert digest(payload) == record['archive_sha256']
        assert len(payload) == record['archive_bytes']
    assert secret not in json.dumps(records)
    assert 'sentinel mathematical draft' not in json.dumps(records)


def test_cancelled_response_does_not_create_archive(tmp_path):
    provider = CompatibleChatProvider(Settings(workspace=tmp_path),
                                     failure_dir=tmp_path/'failures', active=lambda: False)
    with pytest.raises(AgentError) as error:
        provider.preserve_invalid_response('partial')
    assert error.value.code == 'CANCELLED'
    assert not (tmp_path/'failures').exists()


def test_json_repair_feedback_includes_location_without_logging_content(tmp_path):
    sent=[];records=[]
    def respond(request):
        sent.append(json.loads(request.content))
        text=r'{"issues": "x\,y"}' if len(sent)==1 else '{"issues":[],"checked_unit_ids":[],"limitations":[]}'
        return httpx.Response(200,json={'choices':[{'message':{'content':text},'finish_reason':'stop'}]})
    provider=CompatibleChatProvider(Settings(workspace=tmp_path,live_api_enabled=True,
        api_key=SecretStr('synthetic'),llm_streaming=False),record=records.append,
        transport=httpx.MockTransport(respond))
    provider.generate('reviewer_math',{},MathReview)
    error=next(r for r in records if 'validation_errors' in r)['validation_errors'][0]
    assert error['message']=='Invalid \\escape' and error['line']==1 and error['column']>0
    assert 'column' in sent[1]['messages'][-1]['content']
    assert '所有TeX反斜杠' in sent[1]['messages'][-1]['content']
    assert 'x\\,y' not in json.dumps(records)
