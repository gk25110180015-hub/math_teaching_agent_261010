"""Offline append-only regression; answer text here is hand-authored, not live API output."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from math_agent.answer_completion import (
    AnswerCompletion, AnswerCompletionError, apply_answer_completion,
    missing_answer_targets, propose_context,
)
from math_agent.mathcheck import check_math
from math_agent.util import digest

pytestmark = pytest.mark.unit
FIXTURE = Path(__file__).parent / 'fixtures' / 'answer_completion_ch02_s02.json'
TARGETS = ['S02.U18', 'S02.U19', 'S02.U20']


@pytest.fixture(autouse=True)
def disable_real_api(monkeypatch):
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')
    monkeypatch.setenv('MATH_AGENT_API_KEY', '')
    monkeypatch.setenv('MATH_AGENT_LLM_STREAMING', 'false')


@pytest.fixture
def source():
    return json.loads(FIXTURE.read_bytes())


@pytest.fixture
def reply():
    return {'section_id': 'S02', 'answers': [
        {'target_id': TARGETS[0], 'tex': r'(1)通项趋于 $2/3\ne0$，故发散。(2)通项趋于零，单凭必要条件不能判断；这是调和级数删去前两项，仍发散。(3)通项绝对值趋于1，通项不趋于零，故发散。'},
        {'target_id': TARGETS[1], 'tex': r'由已知两级数收敛，线性组合之和为 $3\cdot2-2(-1)=8$。首项再增加5后和为13，仍收敛。反向推断不成立：取 $a_n=1,b_n=-1$，合并后各项为零，而两原级数都发散。'},
        {'target_id': TARGETS[2], 'tex': r'几何级数的余项为 $r_n=2^{-n}$。$2^{-9}=1/512>1/1000$，$2^{-10}=1/1024<1/1000$，故最小正整数为10。首项从 $1/2$ 改为10，和增加 $19/2$，新和为 $21/2$；对 $n\ge1$，第n个余项不变。'},
    ]}


def integer(value):
    return {'op': 'Integer', 'value': value}


def calculation(request_id='NEW.C1', unit_id='S02.U19.answer'):
    return {'id': request_id, 'unit_id': unit_id, 'kind': 'equivalence', 'assumptions': {},
            'lhs': {'op': 'Add', 'args': [
                {'op': 'Mul', 'args': [integer(3), integer(2)]},
                {'op': 'Mul', 'args': [integer(-2), integer(-1)]},
            ]}, 'rhs': integer(8)}


def test_real_fixture_is_exact_preserved_candidate(source):
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == 'fbe0234a6255d1dbb6d9a5aea13b907475df12024956309f831901516e14140b'
    assert len(source['units']) == 20
    assert len(source['calculations']) == 3
    assert missing_answer_targets(source) == TARGETS
    assert source['units'][15]['kind'] == 'solution'
    assert source['units'][15]['relates_to'] == 'S02.U15'


def test_multi_target_append_preserves_every_original_field(source, reply):
    source['metadata'] = {'nested': [1, {'provenance': 'keep'}]}
    source['units'][0]['metadata'] = {'source_spans': [{'start': 7, 'end': 11}]}
    source['calculations'][0]['retained_metadata'] = {'existing': True}
    source['uncertainties'] = ['An existing unresolved doubt']
    reply.update(calculations=[calculation()], calculation_limitations=['Only one new equality checked'],
                 uncertainties=['A new doubt remains'])
    original, original_reply = copy.deepcopy(source), copy.deepcopy(reply)
    result, evidence = apply_answer_completion(source, reply)
    assert source == original and reply == original_reply
    assert result['units'][:20] == original['units']
    assert result['calculations'][:3] == original['calculations']
    assert result['metadata'] == original['metadata']
    assert result['uncertainties'] == original['uncertainties'] + reply['uncertainties']
    assert result['calculation_limitations'] == original['calculation_limitations'] + reply['calculation_limitations']
    assert result['units'][20:] == [
        {'id': item['target_id'] + '.answer', 'kind': 'solution', 'tex': item['tex'], 'relates_to': item['target_id']}
        for item in reply['answers']]
    assert missing_answer_targets(result) == []
    assert evidence['status'] == 'APPLIED_UNCHECKED'
    assert evidence['source_section_hash'] == digest(source)
    assert evidence['result_section_hash'] == digest(result)
    assert evidence['new_unit_ids'] == [target + '.answer' for target in TARGETS]
    assert evidence['original_units_preserved'] and evidence['original_calculations_preserved']
    assert all(evidence[key] == 'NOT_RUN' for key in ('math_check', 'normalization', 'teacher_review'))
    result['units'][0]['metadata']['source_spans'][0]['start'] = 999
    result['metadata']['nested'][1]['provenance'] = 'changed'
    assert source == original


def test_context_is_detached_and_read_only_to_source(source):
    original = copy.deepcopy(source)
    context = propose_context(source)
    assert context['source_section_hash'] == digest(source)
    assert [item['target_id'] for item in context['targets']] == TARGETS
    assert [item['answer_unit_id'] for item in context['targets']] == [target + '.answer' for target in TARGETS]
    assert context['remaining_unit_slots'] == 80
    assert context['remaining_calculation_slots'] == 97
    context['existing_section']['units'][0]['tex'] = 'changed'
    context['targets'][0]['problem']['tex'] = 'changed'
    context['calculation_protocol']['request_kinds'].clear()
    assert source == original
    assert propose_context(source)['calculation_protocol']['request_kinds']


def test_reply_order_and_explicit_subset_use_original_target_order(source, reply):
    reply['answers'] = [reply['answers'][2], reply['answers'][0]]
    result, evidence = apply_answer_completion(source, reply, [TARGETS[2], TARGETS[0]])
    assert evidence['target_ids'] == [TARGETS[0], TARGETS[2]]
    assert [unit['relates_to'] for unit in result['units'][20:]] == [TARGETS[0], TARGETS[2]]
    assert missing_answer_targets(result) == [TARGETS[1]]


@pytest.mark.parametrize('targets', [[], ['foreign'], ['S02.U15'], ['S02.U01'], ['S02.U18 '],
                                      [TARGETS[0], TARGETS[0]], [None], 'S02.U18'])
def test_invalid_requested_targets_fail_before_proposal(source, targets):
    with pytest.raises(AnswerCompletionError):
        propose_context(source, targets)


@pytest.mark.parametrize('mode', ['missing', 'extra', 'duplicate', 'wrong_section'])
def test_response_scope_is_exact(source, reply, mode):
    if mode == 'missing':
        reply['answers'].pop()
    elif mode == 'extra':
        reply['answers'].append({'target_id': 'S02.U15', 'tex': 'Rewrite an existing answer'})
    elif mode == 'duplicate':
        reply['answers'][2]['target_id'] = TARGETS[0]
    else:
        reply['section_id'] = 'S99'
    original = copy.deepcopy(source)
    with pytest.raises(AnswerCompletionError):
        apply_answer_completion(source, reply)
    assert source == original


@pytest.mark.parametrize('field', ['units', 'metadata', 'status'])
def test_response_cannot_replace_section_fields(source, reply, field):
    reply[field] = []
    with pytest.raises(ValidationError):
        apply_answer_completion(source, reply)


@pytest.mark.parametrize('field', ['id', 'kind', 'relates_to'])
def test_model_cannot_choose_new_identity_or_relation(source, reply, field):
    reply['answers'][0][field] = 'unapproved'
    with pytest.raises(ValidationError):
        apply_answer_completion(source, reply)


def test_collision_does_not_overwrite_or_invent_another_id(source):
    source['units'].append({'id': 'S02.U18.answer', 'kind': 'explanation', 'tex': 'Existing content'})
    with pytest.raises(AnswerCompletionError, match='collides'):
        propose_context(source)


@pytest.mark.parametrize('original_count, succeeds', [(97, True), (98, False)])
def test_hundred_unit_capacity_boundary(source, reply, original_count, succeeds):
    source['units'].extend({'id': f'FILL.{index}', 'kind': 'explanation', 'tex': 'Preserved'}
                           for index in range(original_count - 20))
    if succeeds:
        result, _ = apply_answer_completion(source, reply)
        assert len(result['units']) == 100
    else:
        with pytest.raises(AnswerCompletionError, match='100-unit'):
            propose_context(source)


def test_duplicate_original_ids_block(source):
    source['units'][0]['id'] = source['units'][1]['id']
    with pytest.raises(AnswerCompletionError, match='unique'):
        missing_answer_targets(source)


def test_invalid_original_kind_type_blocks_without_typeerror(source):
    source['units'][0]['kind'] = []
    with pytest.raises(AnswerCompletionError, match='structurally invalid'):
        missing_answer_targets(source)


@pytest.mark.parametrize('unit_id', ['S02.U19', 'FOREIGN.answer', None, [], {}])
def test_new_calculations_cannot_bind_existing_or_foreign_units(source, reply, unit_id):
    reply['calculations'] = [calculation(unit_id=unit_id)]
    with pytest.raises(AnswerCompletionError, match='new answer unit'):
        apply_answer_completion(source, reply)


@pytest.mark.parametrize('mode', ['existing', 'duplicate', 'fallback'])
def test_calculation_id_collisions_block(source, reply, mode):
    if mode == 'existing':
        reply['calculations'] = [calculation('S02.C01')]
    elif mode == 'duplicate':
        reply['calculations'] = [calculation(), calculation()]
    else:
        source['calculations'][0].pop('id')
        reply['calculations'] = [calculation('C001')]
    with pytest.raises(AnswerCompletionError, match='collides'):
        apply_answer_completion(source, reply)


@pytest.mark.parametrize('field', ['status', 'evidence', 'python'])
def test_new_calculation_fields_cannot_claim_results(source, reply, field):
    request = calculation()
    request[field] = 'PASS'
    reply['calculations'] = [request]
    with pytest.raises(AnswerCompletionError, match='protocol exactly'):
        apply_answer_completion(source, reply)


@pytest.mark.parametrize('mode', ['unsupported', 'oversized', 'nonfinite', 'total_count'])
def test_calculation_limits_are_bounded(source, reply, mode):
    request = calculation()
    if mode == 'unsupported':
        request['kind'] = 'evaluate_python'
    elif mode == 'oversized':
        request['lhs'] = {'op': 'Symbol', 'name': 'x' * 65536}
    elif mode == 'nonfinite':
        request['lhs'] = {'op': 'Integer', 'value': float('nan')}
    else:
        source['calculations'] = [calculation(f'OLD.{index}', 'S02.U16') for index in range(100)]
    reply['calculations'] = [request]
    with pytest.raises(AnswerCompletionError):
        apply_answer_completion(source, reply)


@pytest.mark.parametrize('text', [r'\section{New theory}', r'\input{other.tex}',
    r'\newcommand{\change}{x}', r'\begin{exercise}New question\end{exercise}',
    r'\begin{theorem}New theorem\end{theorem}', r'\documentclass{book}',
    r'\begin{lemma*}New lemma\end{lemma*}', r'\begin{problem}New problem\end{problem}'])
def test_answer_cannot_introduce_document_or_teaching_structure(source, reply, text):
    reply['answers'][0]['tex'] = text
    with pytest.raises(AnswerCompletionError, match='document structure'):
        apply_answer_completion(source, reply)


def test_empty_new_notes_do_not_clear_old_doubts(source, reply):
    source['uncertainties'] = ['Unresolved existing condition']
    reply.update(uncertainties=[], calculation_limitations=[])
    result, _ = apply_answer_completion(source, reply)
    assert result['uncertainties'] == source['uncertainties']
    assert result['calculation_limitations'] == source['calculation_limitations']


def test_absent_optional_source_fields_stay_absent_without_additions(source, reply):
    for field in ('calculations', 'uncertainties', 'calculation_limitations'):
        source.pop(field)
    result, _ = apply_answer_completion(source, AnswerCompletion.model_validate(reply))
    assert not {'calculations', 'uncertainties', 'calculation_limitations'} & result.keys()


def test_second_apply_does_not_duplicate_answers(source, reply):
    result, _ = apply_answer_completion(source, reply)
    with pytest.raises(AnswerCompletionError):
        apply_answer_completion(result, reply)


@pytest.mark.parametrize('field,value', [('tex', ' '), ('target_id', ''), ('tex', 'x' * 30001)],
                         ids=['blank_body', 'blank_target', 'oversized_body'])
def test_bounded_nonblank_answers(source, reply, field, value):
    reply['answers'][0][field] = value
    with pytest.raises(ValidationError):
        apply_answer_completion(source, reply)


def test_actual_bounded_sympy_checker_runs_new_answer_request(source, reply):
    reply['calculations'] = [calculation()]
    result, evidence = apply_answer_completion(source, reply)
    assert evidence['math_check'] == 'NOT_RUN'
    # Isolate the appended request so this tests the new binding, not old evidence.
    checked = check_math({'section_id': result['section_id'], 'units': result['units'][20:],
                          'calculations': result['calculations'][3:], 'uncertainties': []})
    assert checked['status'] == 'PASS', checked
    assert len(checked['evidence']) == 1
    assert checked['evidence'][0]['evidence_type'] == 'symbolic_check_passed'


def test_invalid_ast_remains_unchecked_until_original_checker_rejects(source, reply):
    request = calculation()
    request['lhs'] = {'op': '__import__', 'args': ['os']}
    reply['calculations'] = [request]
    result, evidence = apply_answer_completion(source, reply)
    assert evidence['status'] == 'APPLIED_UNCHECKED'
    checked = check_math({'section_id': result['section_id'], 'units': result['units'][20:],
                          'calculations': result['calculations'][3:]})
    assert checked['status'] != 'PASS'
    assert all(item['evidence_type'] != 'symbolic_check_passed' for item in checked['evidence'])
