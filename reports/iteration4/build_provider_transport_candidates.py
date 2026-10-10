"""Narrow transport fallback fix atop frozen feedback provider; no production edits."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
base = OUT/'feedback-assessment-provider.candidate.py'
assert sha(base) == 'a291ea01f8a8024504aebf4df154353394cf86652405e487caf4b1fed03bdb96'
text = base.read_text(encoding='utf-8')


def replace(old, new):
    global text
    assert text.count(old) == 1, old
    text = text.replace(old, new)


replace('import asyncio\n', 'import asyncio\nimport hashlib\n')
replace("        data_lines = []\n\n        def consume_event(data):", """        data_lines = []
        wire_hash = hashlib.sha256()
        wire_bytes = 0

        def protocol_failure(reason):
            outcome['response_protocol_error'] = reason
            raise AgentError('PROVIDER_STREAM_PROTOCOL', '供应商流式传输协议不完整或无法解析；部分内容不发布，允许临时切换备用模型')

        def consume_event(data):""")
replace("                    raise AgentError('OUTPUT_INCOMPLETE', '流式响应缺少完整停止状态；不发布部分内容')",
        "                    protocol_failure('done_without_stop')")
replace("                if not ''.join(content_parts).strip():\n                    raise AgentError('PROVIDER_RESPONSE', '供应商返回结构错误或空正文')",
        "                if not ''.join(content_parts).strip():\n                    raise AgentError('PROVIDER_EMPTY_RESPONSE', '供应商完成信号未包含正文；保留记录并尝试备用模型')")
replace("            if not isinstance(body, dict) or body.get('error'):\n                raise ValueError('invalid stream event')",
        "            if not isinstance(body, dict):\n                raise ValueError('invalid stream event')\n            if body.get('error'):\n                # An explicit error may represent a business/refusal decision;\n                # do not infer that switching models is permitted.\n                raise AgentError('PROVIDER_RESPONSE', '供应商流式事件明确返回错误状态')")
replace("                    raise ValueError('unsupported completion')",
        "                    raise AgentError('PROVIDER_RESPONSE', '供应商返回未支持的完成类型；未修改业务参数')")
replace("                raise ValueError('not an SSE response')",
        "                # A non-SSE body could hold an explicit business/refusal\n                # decision. Do not infer permission to switch without reading it.\n                raise AgentError('PROVIDER_RESPONSE', '供应商未返回请求的 SSE 格式；保留失败，不推断未读取响应可切换模型')")
replace("            async for chunk in self._bounded_chunks(response):\n                pending += chunk",
        "            async for chunk in self._bounded_chunks(response):\n                wire_hash.update(chunk)\n                wire_bytes += len(chunk)\n                pending += chunk")
replace("            raise AgentError('OUTPUT_INCOMPLETE', '流式连接结束但缺少 [DONE]；不发布部分内容')",
        "            protocol_failure('eof_before_done')")
replace("            raise AgentError('PROVIDER_RESPONSE', '供应商流式响应结构错误或空正文') from None",
        "            protocol_failure('invalid_sse_event_or_envelope')")
replace("            outcome.update({'streaming': True, 'stream_complete': complete,",
        "            outcome.update({'streaming': True, 'stream_complete': complete,\n                            'received_response_bytes': wire_bytes, 'response_bytes_sha256': wire_hash.hexdigest(),")
replace("                            if not isinstance(content, str) or not content.strip():\n                                raise ValueError('empty')",
        "                            if content is None or (isinstance(content, str) and not content.strip()):\n                                outcome.update({'received_content_chars': 0, 'finish_reason': choice.get('finish_reason'),\n                                    'received_response_bytes': len(body_bytes), 'response_bytes_sha256': hashlib.sha256(body_bytes).hexdigest()})\n                                if choice.get('finish_reason') not in (None, 'stop') or message.get('tool_calls') or message.get('function_call'):\n                                    raise AgentError('PROVIDER_RESPONSE', '供应商返回未支持的完成类型；未修改业务参数')\n                                raise AgentError('PROVIDER_EMPTY_RESPONSE', '供应商响应未包含正文；保留记录并尝试备用模型')\n                            if not isinstance(content, str):\n                                raise ValueError('invalid content type')")
candidate = OUT/'provider-transport-recovery.candidate.py'
candidate.write_text(text, encoding='utf-8')
routing = ROOT/'src/math_agent/model_routing.py'
body = routing.read_text(encoding='utf-8')
assert body.count("    'PROVIDER_NETWORK', 'PROVIDER_TOTAL_TIMEOUT',") == 1
body = body.replace("    'PROVIDER_NETWORK', 'PROVIDER_TOTAL_TIMEOUT',", "    'PROVIDER_NETWORK', 'PROVIDER_TOTAL_TIMEOUT',\n    'PROVIDER_EMPTY_RESPONSE', 'PROVIDER_STREAM_PROTOCOL',")
(OUT/'model-routing-transport-recovery.candidate.py').write_text(body, encoding='utf-8')
files = []
for source, name in [('src/math_agent/provider.py', candidate.name),
    ('src/math_agent/model_routing.py', 'model-routing-transport-recovery.candidate.py')]:
    path = ROOT/source
    prepared = OUT/name
    files.append({'source': source, 'candidate': name, 'baseline_sha256': sha(path), 'candidate_sha256': sha(prepared)})
    original = base if source.endswith('provider.py') else path
    patch = ''.join(difflib.unified_diff(original.read_text(encoding='utf-8').splitlines(True),
        prepared.read_text(encoding='utf-8').splitlines(True), fromfile=str(original.relative_to(ROOT)), tofile=source))
    (OUT/(name+'.patch')).write_text(patch, encoding='utf-8')
(OUT/'provider-transport-recovery-manifest.json').write_text(json.dumps({'status': 'CANDIDATE_UNDER_TEST',
    'files': files, 'supersedes_provider_candidate': base.name, 'production_modified': False,
    'real_api': 'NOT_RUN', 'teacher_review': 'NOT_RUN'}, indent=2), encoding='utf-8')
main = OUT/'feedback-assessment-manifest.json'
history = OUT/'feedback-assessment-manifest-before-transport.json'
if not history.exists():
    history.write_bytes(main.read_bytes())
original = json.loads(history.read_bytes())
assert original['status'] == 'READY_FOR_REVIEWED_DEPLOYMENT'
provider_entry, routing_entry = files
original['files'] = [provider_entry if f['source'] == provider_entry['source'] else f for f in original['files']]
original['files'].append(routing_entry)
original.update(status='CANDIDATE_UNDER_TEST', prior_feedback_manifest=history.name,
    prior_feedback_manifest_sha256=sha(history), transport_delta_manifest='provider-transport-recovery-manifest.json',
    test_classification='MOCK_118_PASS_FOR_PRIOR_FEEDBACK_VERSION_TRANSPORT_DELTA_PENDING')
main.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(files))
