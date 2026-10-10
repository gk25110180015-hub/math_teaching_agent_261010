"""Explicit, scoped feedback assessment; candidates and receipts never approve plans."""
import copy
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field

from math_agent.domain import StrictModel
from math_agent.util import AgentError, digest, now, scrub, write_json


class FeedbackUnitEvidence(StrictModel):
    unit_id: str
    quote: str = Field(min_length=4, max_length=6000)
    kind: Literal['statement', 'proof', 'worked_example', 'counterexample', 'model_assumption', 'reference']


class FeedbackObjectiveEvidence(StrictModel):
    section_id: str | None
    field: Literal['objectives', 'exclusions', 'prerequisites', 'lecture.answers_location', 'lecture.exercises', 'lecture.proof_policy', 'lecture.example_focus']
    quote: str = Field(min_length=2, max_length=2000)


class FeedbackItemAssessment(StrictModel):
    id: str
    status: Literal['satisfied', 'supported_improvement', 'rejected_not_supported', 'out_of_scope', 'unresolved']
    reason: str = Field(min_length=12, max_length=6000)
    unit_ids: list[str] = Field(max_length=100)
    repair_unit_ids: list[str] = Field(max_length=100)
    unit_evidence: list[FeedbackUnitEvidence] = Field(max_length=20)
    objective_evidence: list[FeedbackObjectiveEvidence] = Field(max_length=12)
    repair_instruction: str | None = Field(default=None, max_length=6000)


class FeedbackAssessment(StrictModel):
    items: list[FeedbackItemAssessment] = Field(min_length=1, max_length=100)
    limitations: list[str]


def _compact(text):
    return ''.join(text.split())


def extract_feedback_items(feedback_text):
    """Stable IDs from numbered lines; whole original text remains in context.

    Not semantic decomposition: trailing scope paragraphs remain visible in the
    original text and final item's source span. The model cannot change the IDs.
    """
    if not isinstance(feedback_text, str) or not feedback_text.strip() or len(feedback_text) > 10000:
        raise ValueError('Feedback must be nonempty text of at most 10000 characters')
    numbered = list(re.finditer(r'(?m)^(?:F)?(?P<number>\d{1,3})[.．、:)）](?!\d)[ \t]*\S', feedback_text))
    # Only a top-level consecutive list establishes item boundaries. Decimal
    # values and indented mathematical steps do not create hidden feedback IDs.
    if numbered and [int(m['number']) for m in numbered] != list(range(1, len(numbered) + 1)):
        numbered = []
    starts = [match.start() for match in numbered] or [0]
    items = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(feedback_text)
        text = feedback_text[start:end]
        # A narrow statement of the requested evidence, never an assertion that
        # it is supported/in scope. Negative instructions do not create a demand.
        affirmative = re.sub(r'(?:不要|无需|不必|禁止)[^。\n]{0,35}反例', '', text)
        counterexample = bool(re.search(r'(?:补充|补一个|补一项|给出|提供|落实为|展示)[^。\n]{0,24}反例|(?:add|provide|show)\s+(?:a\s+)?counterexample', affirmative, re.I))
        items.append({'id': 'F' + str(index + 1), 'text': text,
                      'source_start': start, 'source_end': end,
                      'requested_counterexample': counterexample})
    if len(items) > 100:
        raise ValueError('Too many independently numbered feedback items')
    return items


def build_feedback_context(plan, units, feedback_record, mock=False):
    text = feedback_record['feedback']
    ids = [unit['id'] for unit in units]
    if len(ids) != len(set(ids)):
        raise ValueError('Feedback assessment requires unique actual unit IDs')
    return {'plan': copy.deepcopy(plan), 'units': copy.deepcopy(units),
        'actual_unit_ids': ids, 'feedback_text': text,
        'feedback_items': extract_feedback_items(text),
        'feedback_source': feedback_record.get('feedback_source', 'user'),
        'source_event': copy.deepcopy(feedback_record.get('source_event', {})), 'mock': bool(mock),
        'instruction': 'Assess every fixed feedback item explicitly against the actual full chapter and approved plan. Feedback is an observation, not proof or scope approval. A valuable supported teaching improvement can require revision even when current mathematics is correct. Do not infer satisfaction from an empty mathematical issue list. Do not alter plan, add units, sign teacher acceptance, or silently ignore an item.'}


def _plan_quotes(plan, evidence):
    section = evidence['section_id']
    source = plan if section is None else next((s for s in plan.get('sections', []) if s['id'] == section), None)
    if source is None:
        return []
    field = evidence['field']
    if field.startswith('lecture.'):
        if section is not None:
            return []
        value = plan.get('lecture', {}).get(field.split('.')[1], [])
    else:
        value = source.get(field, [])
    return [value] if isinstance(value, str) else [item for item in value if isinstance(item, str)]


def validate_assessment(response, context):
    """Validate coverage, scope and literal spans; mathematical meaning is model-reviewed."""
    result = FeedbackAssessment.model_validate(response).model_dump()
    expected = {item['id']: item for item in context['feedback_items']}
    actual = {unit['id']: unit for unit in context['units']}
    ids = [item['id'] for item in result['items']]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError('Feedback receipt must cover every fixed input ID exactly once')
    by_id = {item['id']: item for item in result['items']}
    result['items'] = [by_id[item['id']] for item in context['feedback_items']]
    issues = []
    for item in result['items']:
        if len(item['reason'].strip()) < 12:
            raise ValueError('Feedback reason must contain actual explanatory text')
        targets = item['unit_ids']
        if len(targets) != len(set(targets)) or not set(targets) <= set(actual):
            raise ValueError('Feedback target is not an actual existing unit')
        for span in item['unit_evidence']:
            if len(_compact(span['quote'])) < 4 or span['unit_id'] not in targets or _compact(span['quote']) not in _compact(actual[span['unit_id']]['tex']):
                raise ValueError('Feedback unit evidence is not in its stated actual target')
        for span in item['objective_evidence']:
            if len(_compact(span['quote'])) < 2 or not any(_compact(span['quote']) in _compact(text) for text in _plan_quotes(context['plan'], span)):
                raise ValueError('Feedback plan evidence is absent from the approved plan')
        demonstration_only = context.get('mock') and item['status'] == 'rejected_not_supported'
        if demonstration_only:
            if not item['reason'].startswith('离线演示不评估自然语言反馈'):
                raise ValueError('Mock receipt must explicitly disclaim natural-language assessment')
        elif item['status'] != 'unresolved':
            if (not targets and item['status'] != 'out_of_scope') or set(targets) != {span['unit_id'] for span in item['unit_evidence']}:
                raise ValueError('Every completed feedback disposition needs actual evidence for every target')
        repair_targets = item['repair_unit_ids']
        if len(repair_targets) != len(set(repair_targets)) or not set(repair_targets) <= set(targets):
            raise ValueError('Repair targets must be unique evidenced actual units')
        if item['status'] == 'supported_improvement':
            if not repair_targets:
                raise ValueError('Supported improvement needs explicit actual repair targets')
            if not item['repair_instruction'] or len(item['repair_instruction'].strip()) < 12:
                raise ValueError('Supported teaching improvement needs a concrete scoped repair instruction')
            if not any(span['field'] == 'objectives' or span['field'].startswith('lecture.') for span in item['objective_evidence']):
                raise ValueError('Supported teaching improvement must cite an approved objective')
            evidence = '\n'.join(span['unit_id'] + ':「' + span['quote'] + '」' for span in item['unit_evidence'])
            for target in repair_targets:
                issues.append({'unit_id': target, 'severity': 'review',
                    'message': '反馈教学改进（不等于数学错误）[' + item['id'] + ']：' + item['reason'] + '\n限定修订：' + item['repair_instruction'],
                    'evidence': evidence + '\n批准目标依据：' + json.dumps(item['objective_evidence'], ensure_ascii=False)})
        elif item['repair_instruction'] is not None or repair_targets:
            raise ValueError('Only supported improvements may request a content patch')
        if item['status'] == 'out_of_scope' and not item['objective_evidence']:
            raise ValueError('Out-of-scope disposition needs approved scope evidence')
        if item['status'] == 'satisfied' and expected[item['id']].get('requested_counterexample'):
            examples = [span['quote'] for span in item['unit_evidence'] if span['kind'] == 'counterexample']
            # A warning without even a concrete mathematical relation cannot
            # substantiate a requested counterexample. This is not a proof of the
            # example; conditions and contrasting outcomes are model-reviewed.
            if not examples or not any(re.search(r'=|<|>|\\(?:neq|ne|to|leq|geq)\b', text) for text in examples):
                raise ValueError('A requested counterexample is not satisfied by a general warning')
    return result, issues


def feedback_contract():
    from math_agent.provider import PROMPTS
    return {'version': 1, 'helper_sha256': digest(Path(__file__).read_bytes()),
        'provider_sha256': digest(Path(__file__).with_name('provider.py').read_bytes()),
        'prompt_sha256': digest((PROMPTS / 'reviewer_feedback.md').read_bytes()),
        'schema_sha256': digest(FeedbackAssessment.model_json_schema())}


def mock_feedback_assessment(context):
    return {'items': [{'id': item['id'], 'status': 'rejected_not_supported',
        'reason': '离线演示不评估自然语言反馈；此固定演示没有判断该建议的教学价值，也未据此修改正文，请用真实模型执行逐项核查。',
        'unit_ids': [], 'repair_unit_ids': [], 'unit_evidence': [], 'objective_evidence': [],
        'repair_instruction': None} for item in context['feedback_items']],
        'limitations': ['Mock only: no mathematical, teaching, visual or teacher assessment was performed.']}


class FeedbackReview:
    """One durable verdict per job, approved scope, supplied body and contract."""
    def __init__(self, pipeline, plan, units, feedback_record):
        self.p = pipeline
        self.context = build_feedback_context(plan, units, feedback_record,
            mock=getattr(pipeline, 'run', {}).get('input', {}).get('provider') == 'mock')
        self.identity = {'job_id': getattr(pipeline, 'job', {}).get('id'),
            'plan_hash': plan['hash'], 'plan_revision': plan['revision'],
            'feedback_hash': digest(feedback_record['feedback']),
            'context_hash': digest(self.context), 'contract': feedback_contract(),
            'model_id': getattr(pipeline, 'model_id', 'UNKNOWN'),
            'configured_gpt_model': getattr(pipeline.settings, 'model', 'UNKNOWN')}
        self.key = digest(self.identity)
        self.folder = Path(pipeline.root) / 'feedback-reviews' / self.key[:24]
        self.state_path = self.folder / 'state.json'
        self.state = None

    def _write(self, path, value):
        if all(hasattr(self.p, key) for key in ('store', 'job')):
            with self.p.store.transaction() as connection:
                self.p.store.assert_fence(connection, self.p.job)
                write_json(path, value)
        else:
            write_json(path, value)

    def _save(self):
        self._write(self.state_path, self.state)

    def _read(self, name):
        if Path(name).name != name or name not in self.state['dependencies']:
            raise ValueError('Invalid feedback evidence path')
        raw = (self.folder / name).read_bytes()
        if digest(raw) != self.state['dependencies'][name]:
            raise ValueError('Feedback evidence hash mismatch')
        return json.loads(raw)

    def _evidence(self, name, value):
        path = self.folder / name
        if path.exists():
            if name in self.state['dependencies'] and self._read(name) == value:
                return
            raise AgentError('FEEDBACK_EVIDENCE_BLOCKED', '反馈证据不可覆盖；保留原响应和任务状态')
        self._write(path, value)
        self.state['dependencies'][name] = digest(path.read_bytes())
        self._save()

    def _receipt(self, assessment, status):
        return {'schema_version': 1, 'job_id': self.identity['job_id'],
            'plan_hash': self.identity['plan_hash'], 'plan_revision': self.identity['plan_revision'],
            'feedback_hash': self.identity['feedback_hash'], 'identity_hash': self.key,
            'status': status, 'items': assessment['items'], 'limitations': assessment['limitations'],
            'teacher_review': 'NOT_RUN', 'mock': self.context['mock']}

    def _emit(self, receipt_name):
        receipt = self._read(receipt_name)
        result = {**receipt,
            'evidence_key': (self.folder / receipt_name).relative_to(self.p.settings.workspace).as_posix(),
            'evidence_sha256': self.state['dependencies'][receipt_name]}
        if all(hasattr(self.p, key) for key in ('store', 'job', 'run')):
            with self.p.store.transaction() as connection:
                self.p.store.assert_fence(connection, self.p.job)
                self.p.store.event(connection, self.p.run['id'], 'feedback.reviewed', result)
        return result

    def _pending_assessment(self, reason):
        return {'items': [{'id': item['id'], 'status': 'unresolved', 'reason': reason,
            'unit_ids': [], 'repair_unit_ids': [], 'unit_evidence': [], 'objective_evidence': [],
            'repair_instruction': None} for item in self.context['feedback_items']],
            'limitations': ['No reliable complete item assessment; evidence retained; teacher review NOT_RUN.']}

    def evaluate(self):
        try:
            if self.state_path.exists():
                self.state = json.loads(self.state_path.read_bytes())
                if self.state['identity'] != self.identity or self.state['identity_hash'] != self.key:
                    raise ValueError('Feedback identity mismatch')
                for name in self.state['dependencies']:
                    self._read(name)
                if self._read('input.json') != self.context:
                    raise ValueError('Actual supplied feedback context changed')
                phase = self.state['status']
                if phase in ('REVIEWED', 'UNRESOLVED'):
                    assessment, issues = validate_assessment(self._read(self.state['response_file']), self.context)
                    status = 'unresolved' if any(i['status'] == 'unresolved' for i in assessment['items']) else 'reviewed'
                    if self._read(self.state['receipt_file']) != self._receipt(assessment, status):
                        raise ValueError('Feedback receipt is not justified by its saved response')
                    result = self._emit(self.state['receipt_file'])
                    if status == 'unresolved':
                        raise AgentError('FEEDBACK_REVIEW_BLOCKED', '原逐项反馈仍未可靠判定；同一正文及身份的普通重试不重新抽取裁定')
                    return result, issues
                if phase == 'INVALID':
                    self._emit(self.state['receipt_file'])
                    raise AgentError('FEEDBACK_REVIEW_BLOCKED', '原逐项反馈响应无效；原证据已保留，普通重试不重新抽取通过')
                if phase not in ('CREATED', 'STARTED', 'TRANSPORT_PENDING', 'RESPONSE_RECEIVED'):
                    raise ValueError('Unknown feedback state')
            else:
                self.state = {'schema_version': 1, 'identity': self.identity, 'identity_hash': self.key,
                    'status': 'CREATED', 'created_at': now(), 'calls': 0, 'dependencies': {}}
                self._save()
                self._evidence('input.json', self.context)
            return self._assess()
        except AgentError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AgentError('FEEDBACK_EVIDENCE_BLOCKED', '反馈身份或证据 SHA 校验失败；保留证据，不绕过核查：' + str(exc)) from None

    def _assess(self):
        saved = self.state.get('response_file')
        response = self._read(saved) if saved in self.state['dependencies'] else None
        if response is None:
            previous = self.folder / ('response-' + str(self.state['calls']) + '.json')
            if previous.exists():
                raise AgentError('FEEDBACK_EVIDENCE_BLOCKED', '发现未登记的完整反馈响应；保留原证据，不重新抽取裁定')
            self.state['calls'] += 1
        call = self.state['calls']
        self.state.update(status='STARTED', started_at=now())
        self._save()
        try:
            if response is None:
                response = self.p.provider.generate('reviewer_feedback', self.context, FeedbackAssessment)
                self.state['response_file'] = 'response-' + str(call) + '.json'
                self._evidence(self.state['response_file'], response)
            self.state['status'] = 'RESPONSE_RECEIVED'
            self._save()
            assessment, issues = validate_assessment(response, self.context)
        except Exception as exc:
            from math_agent.model_routing import TRANSIENT_ERROR_CODES
            code = getattr(exc, 'code', None)
            retryable = response is None and not self.state.get('response_file') and code in (
                set(TRANSIENT_ERROR_CODES) | {'PROVIDER_ALL_UNAVAILABLE', 'PROVIDER_NOT_CONFIGURED', 'BUDGET_EXHAUSTED'})
            failure = {'type': type(exc).__name__, 'code': code, 'message': scrub(str(exc))[:3000],
                'at': now(), 'retryable_same_slot': retryable}
            self._evidence('failure-' + str(call) + '.json', failure)
            status = 'transport_pending' if retryable else 'invalid'
            receipt = self._receipt(self._pending_assessment('本次逐项反馈尚未形成可靠裁定；原始输入与失败证据已保存。原因：' + failure['message']), status)
            name = 'receipt-' + str(call) + '-' + status + '.json'
            self._evidence(name, receipt)
            self.state.update(status='TRANSPORT_PENDING' if retryable else 'INVALID', receipt_file=name,
                failure=failure, ended_at=now())
            self._save()
            self._emit(name)
            if code == 'BUDGET_EXHAUSTED':
                raise
            raise AgentError('FEEDBACK_REVIEW_BLOCKED', '逐项反馈未形成可靠完整回执；原输入输出已保留，未把空数学疑点当作反馈完成') from exc
        status = 'unresolved' if any(i['status'] == 'unresolved' for i in assessment['items']) else 'reviewed'
        name = 'receipt-' + str(call) + '-' + status + '.json'
        self._evidence(name, self._receipt(assessment, status))
        self.state.update(status='UNRESOLVED' if status == 'unresolved' else 'REVIEWED',
            receipt_file=name, ended_at=now())
        self._save()
        result = self._emit(name)
        if status == 'unresolved':
            raise AgentError('FEEDBACK_REVIEW_BLOCKED', '逐项反馈仍有未决项；回执和原响应已保留，普通重试不能抽取通过')
        return result, issues
