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
    field: Literal['objectives', 'exclusions', 'prerequisites']
    quote: str = Field(min_length=2, max_length=2000)


class FeedbackItemAssessment(StrictModel):
    id: str
    status: Literal['satisfied', 'supported_improvement', 'rejected_not_supported', 'out_of_scope', 'unresolved']
    reason: str = Field(min_length=12, max_length=6000)
    unit_ids: list[str] = Field(max_length=100)
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
    numbered = list(re.finditer(r'(?m)^[ \t]*(?:F)?\d{1,3}[.．、:)）][ \t]+\S', feedback_text))
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
    value = source.get(evidence['field'], [])
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
        targets = item['unit_ids']
        if len(targets) != len(set(targets)) or not set(targets) <= set(actual):
            raise ValueError('Feedback target is not an actual existing unit')
        for span in item['unit_evidence']:
            if span['unit_id'] not in targets or _compact(span['quote']) not in _compact(actual[span['unit_id']]['tex']):
                raise ValueError('Feedback unit evidence is not in its stated actual target')
        for span in item['objective_evidence']:
            if not any(_compact(span['quote']) in _compact(text) for text in _plan_quotes(context['plan'], span)):
                raise ValueError('Feedback plan evidence is absent from the approved plan')
        demonstration_only = context.get('mock') and item['status'] == 'rejected_not_supported'
        if demonstration_only:
            if not item['reason'].startswith('离线演示不评估自然语言反馈'):
                raise ValueError('Mock receipt must explicitly disclaim natural-language assessment')
        elif item['status'] != 'unresolved':
            if not targets or set(targets) != {span['unit_id'] for span in item['unit_evidence']}:
                raise ValueError('Every completed feedback disposition needs actual evidence for every target')
        if item['status'] == 'supported_improvement':
            if not item['repair_instruction'] or len(item['repair_instruction'].strip()) < 12:
                raise ValueError('Supported teaching improvement needs a concrete scoped repair instruction')
            if not any(span['field'] == 'objectives' for span in item['objective_evidence']):
                raise ValueError('Supported teaching improvement must cite an approved objective')
            evidence = '\n'.join(span['unit_id'] + ':「' + span['quote'] + '」' for span in item['unit_evidence'])
            for target in targets:
                issues.append({'unit_id': target, 'severity': 'review',
                    'message': '反馈教学改进（不等于数学错误）[' + item['id'] + ']：' + item['reason'] + '\n限定修订：' + item['repair_instruction'],
                    'evidence': evidence + '\n批准目标依据：' + json.dumps(item['objective_evidence'], ensure_ascii=False)})
        elif item['repair_instruction'] is not None:
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
