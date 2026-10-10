"""Offline provider replay: diagnostics never rewrite or accept malformed JSON."""
import json
from pathlib import Path

import httpx
import pytest

import math_agent.provider as module
from math_agent.domain import MathReview,WrittenSection
from math_agent.settings import Settings
from math_agent.util import AgentError,digest


def captured(number):
    return (Path(__file__).parent/'fixtures'/f'provider_invalid_escape_ch02_{number}.txt').read_text(encoding='utf-8')


@pytest.mark.parametrize('number,offsets',[(1,[3611,6353,6419]),(2,[6353,6419]),(3,[6353,6419])])
def test_real_three_archives_report_every_invalid_escape_without_rewriting(number,offsets):
    raw=captured(number);before=digest(raw)
    details=module.invalid_json_escape_diagnostics(raw)
    assert [item['offset'] for item in details['issues']]==offsets
    assert not details['truncated']
    assert digest(raw)==before
    with pytest.raises(json.JSONDecodeError):module.extract_json(raw)
    example=json.loads(details['valid_json_example'])
    assert example['tex']==r'a \leq b; \qquad c'


@pytest.mark.parametrize('raw',[
    json.dumps({'tex':r'\leq \qquad \\ \" \/'}),
    r'{"text":"\"quoted\" \\q \/ \b \f \n \r \t \u4e2d \uD83D\uDE00"}',
    r'{"path":"C:\\new\\test","value":"end\\"}',
])
def test_valid_escapes_including_quotes_slashes_and_unicode_are_not_flagged(raw):
    json.loads(raw)
    assert module.invalid_json_escape_diagnostics(raw)['issues']==[]


@pytest.mark.parametrize('raw',[
    r'{"tex":"\u12G4"}',r'{"tex":"\u12"}',r'{"tex":"\u"}',
    '{\n"汉字":"前文",\n"tex":"\\q"}',r'{"tex":"\U1234"}',
])
def test_error_coordinates_match_standard_json_decoder(raw):
    with pytest.raises(json.JSONDecodeError) as error:json.loads(raw)
    first=module.invalid_json_escape_diagnostics(raw)['issues'][0]
    assert (first['offset'],first['line'],first['column'])==(error.value.pos,error.value.lineno,error.value.colno)
    assert raw[first['excerpt_start']:first['excerpt_end']]==first['excerpt']


def test_unterminated_string_and_escape_outside_strings_are_not_repaired():
    raw='{"tex":"unfinished'+chr(92)
    details=module.invalid_json_escape_diagnostics(raw)
    assert details['issues'][0]['kind']=='trailing_backslash'
    assert module.invalid_json_escape_diagnostics(r'\q {"tex":"ok"}')['issues']==[]
    with pytest.raises(json.JSONDecodeError):module.extract_json(raw)


def test_redaction_precedes_excerpt_slicing_and_keeps_coordinates(monkeypatch):
    secret='SYNTHETIC_PRIVATE_'+'x'*100+'\\q_END'
    monkeypatch.setenv('MATH_AGENT_API_KEY',secret)
    raw='{"tex":"'+secret+r' \z"}'
    details=module.invalid_json_escape_diagnostics(raw,secret=secret)
    serialized=json.dumps(details)
    assert secret not in serialized and 'PRIVATE_' not in serialized and 'x'*8 not in serialized
    assert details['issues'][0]['offset']==raw.index('\\q')
    generic=module.invalid_json_escape_diagnostics(r'{"tex":"Bearer sk-SYNTHETIC_CREDENTIAL_123 \z"}')
    assert 'SYNTHETIC_CREDENTIAL' not in json.dumps(generic)


def test_diagnostic_work_issue_count_and_serialized_length_are_bounded():
    raw='{"tex":"'+r'\q'*20000+'"}'
    details=module.invalid_json_escape_diagnostics(raw)
    assert len(details['issues'])<=module.MAX_ESCAPE_DIAGNOSTIC_ITEMS and details['truncated']
    assert len(json.dumps(details,ensure_ascii=False,sort_keys=True,separators=(',',':')))<=module.MAX_ESCAPE_DIAGNOSTIC_CHARS
    late='{"tex":"'+'a'*(module.MAX_ESCAPE_SCAN_CHARS+10)+r'\q"}'
    result=module.invalid_json_escape_diagnostics(late)
    assert result['issues']==[] and result['truncated']
    assert result['scanned_characters']<=module.MAX_ESCAPE_SCAN_CHARS


def test_scan_boundary_does_not_invent_an_invalid_unicode_escape(monkeypatch):
    raw=r'{"tex":"abc\u1234"}'
    monkeypatch.setattr(module,'MAX_ESCAPE_SCAN_CHARS',raw.index('\\u')+3)
    result=module.invalid_json_escape_diagnostics(raw)
    assert result['issues']==[] and result['truncated']


def test_overlapping_configured_and_environment_credentials_are_fully_masked(monkeypatch):
    short='synthetic-private';long=short+'-long-suffix-'+r'\q'
    monkeypatch.setenv('MATH_AGENT_API_KEY',short)
    result=module.invalid_json_escape_diagnostics('{"tex":"'+long+r' \z"}',secret=long)
    assert 'long-suffix' not in json.dumps(result) and short not in json.dumps(result)


def fake_provider(tmp_path,monkeypatch,texts):
    monkeypatch.setenv('MATH_AGENT_API_KEY','synthetic-transport-only-key')
    sent=[];records=[];requests=[]
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':texts[len(sent)-1]},'finish_reason':'stop'}]})
    settings=Settings(workspace=tmp_path,live_api_enabled=True,llm_streaming=False)
    provider=module.CompatibleChatProvider(settings,transport=httpx.MockTransport(handler),
        record=records.append,before_request=requests.append,failure_dir=tmp_path/'failures')
    return provider,sent,records,requests


def test_real_archives_replayed_through_mock_http_remain_three_failed_requests(tmp_path,monkeypatch):
    texts=[captured(i) for i in (1,2,3)]
    provider,sent,records,requests=fake_provider(tmp_path,monkeypatch,texts)
    with pytest.raises(AgentError) as error:provider.generate('writer_lecture_section',{'fixture':'offline'},WrittenSection)
    assert error.value.code=='INVALID_MODEL_JSON' and len(sent)==len(requests)==3
    assert [item['messages'][-2]['content'] for item in sent[1:]]==texts[:2]
    first_feedback=sent[1]['messages'][-1]['content'];second_feedback=sent[2]['messages'][-1]['content']
    for value in ('3611','6353','6419','valid_json_example'):assert value in first_feedback
    assert '6353' in second_feedback and '6419' in second_feedback
    assert len(first_feedback)<module.MAX_ESCAPE_DIAGNOSTIC_CHARS+1500
    assert r'\qquad' not in json.dumps(records,ensure_ascii=False)
    archived=[item for item in records if 'archive_sha256' in item]
    assert len(archived)==3 and len({item['invalid_response_archive'] for item in archived})==3
    for item,raw in zip(archived,texts):assert Path(item['invalid_response_archive']).read_text(encoding='utf-8')==raw
    assert all('output_hash' not in item for item in records)


def test_fenced_response_diagnostics_use_json_decoder_document_coordinates(tmp_path,monkeypatch):
    raw='  ```json\n'+r'{"issues":[],"checked_unit_ids":[],"limitations":["x\q"]}'+'\n```  '
    valid=json.dumps({'issues':[],'checked_unit_ids':[],'limitations':[]})
    provider,sent,records,requests=fake_provider(tmp_path,monkeypatch,[raw,valid])
    assert provider.generate('reviewer_math',{},MathReview)['issues']==[]
    assert len(requests)==2
    record=next(item for item in records if 'validation_errors' in item)
    assert record['validation_errors'][0]['line']==1
    feedback=sent[1]['messages'][-1]['content']
    assert 'JSON decoder document' in feedback and 'x' in feedback
    assert 'synthetic-transport-only-key' not in feedback+json.dumps(records)


@pytest.mark.parametrize('limit',[0,1])
def test_diagnostics_do_not_extend_configured_schema_retry_budget(tmp_path,monkeypatch,limit):
    provider,sent,records,requests=fake_provider(tmp_path,monkeypatch,[captured(1)]*3)
    provider.settings=provider.settings.model_copy(update={'max_schema_repair_attempts':limit})
    with pytest.raises(AgentError) as error:provider.generate('writer_lecture_section',{},WrittenSection)
    assert error.value.code=='INVALID_MODEL_JSON' and len(sent)==len(requests)==limit+1
    assert len(list((tmp_path/'failures').glob('invalid-*.txt')))==limit+1


def test_diagnostic_feedback_cannot_bypass_outer_request_budget(tmp_path,monkeypatch):
    provider,sent,records,requests=fake_provider(tmp_path,monkeypatch,[captured(1)]*3)
    def bounded(metadata):
        if requests:raise AgentError('BUDGET_EXHAUSTED','synthetic caller cap')
        requests.append(metadata)
    provider.before_request=bounded
    with pytest.raises(AgentError) as error:provider.generate('writer_lecture_section',{},WrittenSection)
    assert error.value.code=='BUDGET_EXHAUSTED' and len(sent)==len(requests)==1
    assert len(list((tmp_path/'failures').glob('invalid-*.txt')))==1
