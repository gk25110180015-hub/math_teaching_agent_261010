"""Prepare recovery for a provider error envelope inside an HTTP-200 SSE stream."""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; REPORTS=Path(__file__).resolve().parent
OUT=REPORTS/'sse-error-recovery-candidate'; OUT.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
provider=(ROOT/'src/math_agent/provider.py').read_text(encoding='utf-8')
old="""            if body.get('error'):
                # An explicit error may represent a business/refusal decision;
                # do not infer that switching models is permitted.
                raise AgentError('PROVIDER_RESPONSE', '供应商流式事件明确返回错误状态')
"""
new="""            if body.get('error'):
                # This is a provider control envelope, never completed teaching
                # content. Keep its bounded diagnostics, not hidden reasoning.
                error = body['error']
                diagnostic = ({key: error[key] for key in ('code', 'type', 'message', 'status', 'param')
                               if key in error and isinstance(error[key], (str, int, float, bool, type(None)))}
                              if isinstance(error, dict) else {'message': str(error)[:2000]})
                diagnostic = {key: value[:2000] if isinstance(value, str) else value
                              for key, value in diagnostic.items()}
                outcome['stream_error_event_sha256'] = digest(data)
                outcome['stream_error_code'] = self._scrub(str(diagnostic.get('code', '')))[:200]
                outcome['stream_error_type'] = self._scrub(str(diagnostic.get('type', '')))[:200]
                outcome.update(self.preserve_invalid_response(canonical({'provider_error': diagnostic})))
                category = ' '.join(str(diagnostic.get(key, '')).casefold() for key in ('code', 'type'))
                blocked = ('policy', 'content_filter', 'moderation', 'safety', 'refusal',
                           'invalid_request', 'invalid_parameter', 'context_length',
                           'unsupported_parameter', 'bad_request')
                if any(token in category for token in blocked):
                    raise AgentError('PROVIDER_RESPONSE', '供应商明确返回内容限制或请求参数错误；诊断已保留')
                raise AgentError('PROVIDER_STREAM_ERROR', '供应商在流式传输中返回 API 错误；诊断已保留并尝试备用模型')
"""
assert provider.count(old)==1
provider=provider.replace(old,new,1)
routing=(ROOT/'src/math_agent/model_routing.py').read_text(encoding='utf-8')
needle="'PROVIDER_EMPTY_RESPONSE', 'PROVIDER_STREAM_PROTOCOL',"
assert routing.count(needle)==1
routing=routing.replace(needle,needle+" 'PROVIDER_STREAM_ERROR',",1)
files=[]
for target,text,name in [('src/math_agent/provider.py',provider,'provider.py'),
                         ('src/math_agent/model_routing.py',routing,'model_routing.py')]:
    ast.parse(text); path=OUT/name; path.write_text(text,encoding='utf-8',newline='\n')
    files.append(dict(source=target,candidate=path.relative_to(REPORTS).as_posix(),
        baseline_sha256=sha(ROOT/target),candidate_sha256=sha(path)))
test=REPORTS/'test_sse_error_recovery.candidate.py'
files.append(dict(source='tests/test_sse_error_recovery.py',candidate=test.name,
    baseline_sha256=None,candidate_sha256=sha(test)))
(OUT/'manifest.json').write_text(json.dumps(dict(status='CANDIDATE_NOT_VALIDATED',files=files,
    actual_failure='CH02 request 128, call event2365/error2370; original SSE error body was not archived, only wire SHA/361 bytes; exact original vendor code unknown'),indent=2),encoding='utf-8')
print('SSE error recovery candidate prepared; production unchanged')
