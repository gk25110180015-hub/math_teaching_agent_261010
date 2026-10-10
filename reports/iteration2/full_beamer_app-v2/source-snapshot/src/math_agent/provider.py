"""Text-only compatible chat provider; capabilities never inferred from HTTP 200."""
import asyncio
import json
import time
from pathlib import Path
from typing import Protocol
import httpx
from pydantic import BaseModel, ValidationError
from .settings import Settings
from .util import AgentError, canonical, digest, now, scrub

PROMPTS = Path(__file__).parent / 'prompts'
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def _reported_usage(value):
    if not isinstance(value, dict):
        return None
    return {k: v for k, v in value.items() if k in ('prompt_tokens', 'completion_tokens', 'total_tokens')
            and type(v) is int and v >= 0} or None


class LLMProvider(Protocol):
    def generate(self, role: str, context: dict, schema: type[BaseModel]) -> dict: ...


def extract_json(text: str):
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        lines = text.splitlines()
        text = '\n'.join(lines[1:-1])
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('Expected one JSON object')
    return value


class CompatibleChatProvider:
    def __init__(self, settings: Settings, before_request=None, record=None, active=None, transport=None):
        self.settings = settings
        self.before_request = before_request or (lambda metadata: None)
        self.record = record or (lambda metadata: None)
        self.active = active or (lambda: True)
        self.transport = transport

    async def _await_active(self, awaitable):
        """Cancel outstanding network reads even when no new SSE bytes arrive."""
        task = asyncio.ensure_future(awaitable)
        try:
            while True:
                if not self.active():
                    raise AgentError('CANCELLED', '任务已取消；未完成的 API 响应不发布')
                done, _ = await asyncio.wait({task}, timeout=0.2)
                if done:
                    return task.result()
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _bounded_chunks(self, response):
        iterator = response.aiter_bytes().__aiter__()
        received = 0
        while True:
            try:
                chunk = await self._await_active(iterator.__anext__())
            except StopAsyncIteration:
                return
            received += len(chunk)
            if received > MAX_RESPONSE_BYTES:
                raise AgentError('PROVIDER_OVERSIZE', '供应商输出超出单次上限')
            yield chunk

    async def _read_sse(self, response, outcome):
        content_parts = []
        usage = None
        response_id = ''
        finish_reason = None
        complete = False
        pending = b''
        data_lines = []

        def consume_event(data):
            nonlocal usage, response_id, finish_reason, complete
            if data == '[DONE]':
                if finish_reason != 'stop':
                    raise AgentError('OUTPUT_INCOMPLETE', '流式响应缺少完整停止状态；不发布部分内容')
                if not ''.join(content_parts).strip():
                    raise AgentError('PROVIDER_RESPONSE', '供应商返回结构错误或空正文')
                if not self.active():
                    raise AgentError('CANCELLED', '取消后的 API 响应已丢弃，不发布')
                complete = True
                return
            body = json.loads(data)
            if not isinstance(body, dict) or body.get('error'):
                raise ValueError('invalid stream event')
            if isinstance(body.get('id'), str):
                response_id = scrub(body['id'])[:200]
            if body.get('usage') is not None:
                usage = _reported_usage(body['usage'])
            choices = body.get('choices')
            if not isinstance(choices, list) or len(choices) > 1:
                raise ValueError('invalid stream choices')
            for choice in choices:
                if not isinstance(choice, dict) or choice.get('index', 0) != 0:
                    raise ValueError('invalid stream choice')
                delta = choice.get('delta', {})
                if not isinstance(delta, dict):
                    raise ValueError('invalid delta')
                reason = choice.get('finish_reason')
                if delta.get('refusal') or reason == 'content_filter':
                    if reason == 'content_filter':
                        finish_reason = reason
                    raise AgentError('PROVIDER_REFUSAL', '供应商拒绝本次内容')
                if reason == 'length':
                    finish_reason = reason
                    raise AgentError('OUTPUT_TRUNCATED', '输出被截断；请缩小计划单元后重试，不自动补成成功')
                if reason not in (None, 'stop') or delta.get('tool_calls') or delta.get('function_call'):
                    if reason in ('tool_calls', 'function_call'):
                        finish_reason = reason
                    raise ValueError('unsupported completion')
                fragment = delta.get('content')
                if fragment is not None and not isinstance(fragment, str):
                    raise ValueError('invalid stream content')
                if finish_reason is not None and (fragment or reason is not None):
                    raise ValueError('content after finish')
                if fragment:
                    content_parts.append(fragment)
                if reason is not None:
                    finish_reason = reason

        try:
            if response.headers.get('content-type', '').split(';')[0].strip().lower() != 'text/event-stream':
                raise ValueError('not an SSE response')
            async for chunk in self._bounded_chunks(response):
                pending += chunk
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    line = line.removesuffix(b'\r').decode('utf-8')
                    if not line:
                        if data_lines:
                            consume_event('\n'.join(data_lines))
                            data_lines = []
                            if complete:
                                return scrub(''.join(content_parts))
                    elif line.startswith('data:'):
                        value = line[5:]
                        data_lines.append(value[1:] if value.startswith(' ') else value)
                    # Comments and SSE event/id/retry fields carry no completion text.
            raise AgentError('OUTPUT_INCOMPLETE', '流式连接结束但缺少 [DONE]；不发布部分内容')
        except (KeyError, IndexError, TypeError, ValueError):
            raise AgentError('PROVIDER_RESPONSE', '供应商流式响应结构错误或空正文') from None
        finally:
            outcome.update({'streaming': True, 'stream_complete': complete,
                            'finish_reason': finish_reason, 'usage': usage, 'price': None,
                            'response_id': response_id, 'received_content_chars': sum(map(len, content_parts)),
                            'billing_uncertain': not complete or usage is None})

    async def _request(self, messages, role):
        s = self.settings
        if not s.live_api_enabled or not s.api_key.get_secret_value():
            raise AgentError('PROVIDER_NOT_CONFIGURED', '真实 API 未启用或 MATH_AGENT_API_KEY 未设置；不会使用聊天中的密钥')
        url = s.api_base_url.rstrip('/') + '/chat/completions'
        timeout = httpx.Timeout(connect=s.llm_connect_timeout_seconds, read=s.llm_read_timeout_seconds,
                                write=30, pool=15)
        temperature = 0.1 if 'reviewer' in role else (0.7 if role == 'check' else 0.4)
        payload = {'model': s.model, 'messages': messages, 'temperature': temperature}
        if s.llm_streaming:
            payload['stream'] = True
        metadata = {'role': role, 'model': s.model, 'streaming': s.llm_streaming}
        try:
            async with asyncio.timeout(s.llm_total_timeout_seconds):
                async with httpx.AsyncClient(timeout=timeout, transport=self.transport, trust_env=False, follow_redirects=False) as client:
                    for attempt in range(s.max_network_retries + 1):
                        if not self.active():
                            raise AgentError('CANCELLED', '请求前任务已取消')
                        metadata = {'role': role, 'model': s.model, 'attempt': attempt + 1, 'input_hash': digest(messages), 'temperature': temperature, 'timestamp': now(), 'streaming': s.llm_streaming}
                        self.before_request(metadata)
                        started = time.monotonic()
                        response = None
                        outcome = {'usage': None, 'price': None, 'billing_uncertain': True}
                        try:
                            request = client.build_request('POST', url, headers={'Authorization': 'Bearer ' + s.api_key.get_secret_value()}, json=payload)
                            response = await self._await_active(client.send(request, stream=True))
                            outcome.update({'http_status': response.status_code, 'request_id': scrub(response.headers.get('x-request-id', ''))[:200]})
                            self.record({**metadata, **outcome, 'headers_elapsed_seconds': round(time.monotonic() - started, 3)})
                            if response.status_code in (401, 403):
                                raise AgentError('PROVIDER_AUTH', '供应商拒绝密钥或模型权限（401/403）；不自动重试')
                            if response.status_code in (429, 500, 502, 503, 504):
                                if attempt < s.max_network_retries:
                                    try:
                                        delay = min(max(float(response.headers.get('Retry-After', 2 ** attempt)), 0), 10)
                                    except ValueError:
                                        delay = 2 ** attempt
                                    await response.aclose()
                                    await self._await_active(asyncio.sleep(delay))
                                    continue
                                raise AgentError('PROVIDER_RATE_LIMIT' if response.status_code == 429 else 'PROVIDER_UNAVAILABLE', '供应商临时失败，有限重试已耗尽')
                            if response.status_code != 200:
                                raise AgentError('PROVIDER_HTTP', f'供应商 HTTP {response.status_code}；未自动删除业务参数')
                            if s.llm_streaming:
                                return await self._read_sse(response, outcome)
                            body_bytes = b''.join([chunk async for chunk in self._bounded_chunks(response)])
                            try:
                                body = json.loads(body_bytes)
                                choice = body['choices'][0]
                                message = choice['message']
                                content = message.get('content')
                                if choice.get('finish_reason') == 'length':
                                    raise AgentError('OUTPUT_TRUNCATED', '输出被截断；请缩小计划单元后重试，不自动补成成功')
                                if message.get('refusal') or choice.get('finish_reason') == 'content_filter':
                                    raise AgentError('PROVIDER_REFUSAL', '供应商拒绝本次内容')
                                if not isinstance(content, str) or not content.strip():
                                    raise ValueError('empty')
                                if not self.active():
                                    raise AgentError('CANCELLED', '取消后的 API 响应已丢弃，不发布')
                                usage = _reported_usage(body.get('usage'))
                                outcome.update({'usage': usage, 'price': None, 'billing_uncertain': usage is None,
                                                'response_id': scrub(body.get('id', ''))[:200]})
                                return scrub(content)
                            except (KeyError, IndexError, TypeError, ValueError):
                                raise AgentError('PROVIDER_RESPONSE', '供应商返回结构错误或空正文') from None
                        except httpx.TimeoutException:
                            outcome.update({'status': 'TIMEOUT', 'billing_uncertain': True})
                            raise AgentError('PROVIDER_TIMEOUT', 'API 超时；服务端可能已处理并计费，重试会保留此记录') from None
                        except httpx.HTTPError:
                            outcome.update({'status': 'NETWORK_ERROR', 'billing_uncertain': True})
                            raise AgentError('PROVIDER_NETWORK', 'API 网络连接失败；未记录请求头或异常正文') from None
                        finally:
                            if response is not None:
                                await response.aclose()
                            self.record({**metadata, **outcome, 'elapsed_seconds': round(time.monotonic() - started, 3)})
        except TimeoutError:
            self.record({**metadata, 'status': 'TOTAL_TIMEOUT', 'usage': None, 'price': None, 'billing_uncertain': True})
            raise AgentError('PROVIDER_TOTAL_TIMEOUT', 'API 总截止时间已到；调用可能已计费') from None

    def check(self):
        return asyncio.run(self._request([{'role': 'user', 'content': '只回复 OK。'}], 'check'))

    def generate(self, role, context, schema):
        path = PROMPTS / (role + '.md')
        instruction = path.read_text(encoding='utf-8')
        messages = [{'role': 'system', 'content': instruction + '\n必须只输出一个 JSON 对象，精确遵循 schema：\n' + canonical(schema.model_json_schema())},
                    {'role': 'user', 'content': 'UNTRUSTED_SOURCE_DATA\n' + canonical(context) + '\nEND_UNTRUSTED_SOURCE_DATA'}]
        last_errors = []
        for attempt in range(self.settings.max_schema_repair_attempts + 1):
            text = asyncio.run(self._request(messages, role))
            try:
                result = schema.model_validate(extract_json(text))
                self.record({'role': role, 'prompt_version': 1, 'prompt_hash': digest(instruction), 'schema_attempt': attempt + 1, 'output_hash': digest(result.model_dump())})
                return result.model_dump()
            except (ValidationError, ValueError) as exc:
                # Do not log returned content or Pydantic error input values.
                errors = [{'loc': list(e['loc']), 'type': e['type']} for e in exc.errors(include_input=False)] if isinstance(exc, ValidationError) else [{'type': 'invalid_json'}]
                last_errors = errors
                self.record({'role': role, 'schema_attempt': attempt + 1, 'validation_errors': errors, 'invalid_response_hash': digest(text)})
                messages = messages[:2] + [{'role': 'assistant', 'content': text}, {'role': 'user', 'content': '请修复这些结构错误后重新返回完整 JSON。不得补造通过状态：' + canonical(errors)}]
        raise AgentError('INVALID_MODEL_JSON', '结构修复预算耗尽；错误：' + canonical(last_errors))


class MockProvider:
    """Deterministic synthetic demo only. Never substitutes for a live request."""
    def generate(self, role, context, schema):
        if role == 'planner_lecture':
            value = {'title': context['topic'] + '（离线演示）',
                     'objectives': ['演示可恢复的讲义生成流程'], 'prerequisites': ['实数与不等式'],
                     'sections': [{'id':'S01','title':'数列极限的定义','objectives':['理解 epsilon 定义'], 'required_kinds':['definition','theorem','example','solution'], 'prerequisites':[]},
                                  {'id':'S02','title':'极限的运算','objectives':['验证极限运算'], 'required_kinds':['definition','theorem','example','solution'], 'prerequisites':['S01']}],
                     'symbols': {'a_n':'实数列', 'epsilon':'正实数'}, 'exclusions':['未指定专题的真实教学验收']}
        elif role == 'writer_lecture_section':
            sid = context['section']['id']
            if sid == 'S01':
                units = [
                    {'kind':'definition', 'tex':r'称实数列 $a_n$ 收敛于 $a$，如果对每个 $\varepsilon>0$，存在正整数 $N$，使得所有 $n>N$ 都满足 $|a_n-a|<\varepsilon$。'},
                    {'kind':'theorem', 'tex':r'收敛实数列的极限唯一。'},
                    {'kind':'proof', 'tex':r'若极限 $a\ne b$，取 $\varepsilon=|a-b|/3>0$。由两次收敛定义，充分大的 $n$ 同时满足 $|a_n-a|<\varepsilon$ 和 $|a_n-b|<\varepsilon$。三角不等式给出 $|a-b|<2|a-b|/3$，矛盾。'},
                    {'kind':'example', 'tex':r'证明 $a_n=1/n$ 收敛于 $0$。'},
                    {'kind':'solution', 'tex':r'任取 $\varepsilon>0$，取正整数 $N>1/\varepsilon$。当 $n>N$ 时，$|1/n-0|=1/n<1/N<\varepsilon$。故所求极限为 $0$。'}]
            else:
                units = [
                    {'kind':'definition','tex':r'若 $a_n\to a$，则 $r_n=a_n-a$ 称为余项，并且 $r_n\to0$。'},
                    {'kind':'theorem','tex':r'若实数列 $a_n\to a$ 且 $b_n\to b$，则 $a_n+b_n\to a+b$。'},
                    {'kind':'proof','tex':r'任取 $\varepsilon>0$，分别对两个收敛数列使用 $\varepsilon/2$。充分大的 $n$ 满足 $|(a_n+b_n)-(a+b)|\leq |a_n-a|+|b_n-b|<\varepsilon$。'},
                    {'kind':'example','tex':r'求 $\lim_{n\to\infty}(2+1/n)$。'},
                    {'kind':'solution','tex':r'常数列 $2$ 的极限为 $2$，且 $1/n\to0$。由加法法则，所求极限为 $2$。'}]
            for i,u in enumerate(units):
                u.update(id=f'{sid}.U{i+1:02}', relates_to=(f'{sid}.U02' if u['kind']=='proof' else f'{sid}.U04' if u['kind']=='solution' else None))
            if context['plan'].get('lecture', {}).get('exercises') != 'none':
                constant='3' if sid=='S01' else '5'
                units.append({'id':sid+'.E01','kind':'exercise','tex':r'按定义证明 $'+constant+r'/n\to0$。','relates_to':None})
                units.append({'id':sid+'.A01','kind':'solution','tex':r'取正整数 $N>'+constant+r'/\varepsilon$，则 $n>N$ 时 $'+constant+r'/n<\varepsilon$。','relates_to':sid+'.E01'})
            value = {'section_id':sid,'units':units,'calculations':[], 'uncertainties':[]}
        elif role == 'reviewer_math':
            value = {'issues':[], 'checked_unit_ids':[u['id'] for u in context['units']], 'limitations':['Mock reviewer only; no real model review performed.']}
        else:
            raise AgentError('MOCK_ROLE', '演示 provider 不支持此修复职责')
        return schema.model_validate(value).model_dump()
