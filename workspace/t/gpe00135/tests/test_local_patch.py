"""Offline strict-patch boundaries; captured failures are never sanitized into approval."""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from math_agent.local_patch import LocalPatch, LocalPatchError, apply_local_patch
from math_agent.mathcheck import check_math
from math_agent.util import digest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def disable_api(monkeypatch):
    monkeypatch.setenv('MATH_AGENT_API_KEY', '')
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')
    monkeypatch.setenv('MATH_AGENT_LLM_STREAMING', 'false')


def integer(value):
    return {'op': 'Integer', 'value': value}


def calculation(request_id='C1', unit_id='U2', expected=2):
    return {'id': request_id, 'unit_id': unit_id, 'kind': 'equivalence', 'assumptions': {},
            'lhs': {'op': 'Add', 'args': [integer(1), integer(1)]}, 'rhs': integer(expected)}


@pytest.fixture
def section():
    return {'section_id': 'S01', 'units': [
        {'id': 'U1', 'kind': 'theorem', 'tex': '一加一等于二。', 'relates_to': None, 'metadata': {'source': [1, 2]}},
        {'id': 'U2', 'kind': 'proof', 'tex': '原证明。', 'relates_to': 'U1', 'metadata': {'source': [3, 4]}},
        {'id': 'U3', 'kind': 'explanation', 'tex': '保持此解释。', 'relates_to': None}],
        'calculations': [calculation(expected=3), calculation('C2', 'U3')],
        'uncertainties': ['必须保留的旧疑点'], 'calculation_limitations': ['既有覆盖限制'],
        'metadata': {'nested': [{'source': 'original'}]}}


@pytest.fixture
def patch():
    return {'section_id': 'S01', 'replacements': [{'unit_id': 'U2', 'tex': r'按整数加法，$1+1=2$。'}]}


def test_exact_target_text_only_preserves_all_original_data(section, patch):
    before, reply_before = copy.deepcopy(section), copy.deepcopy(patch)
    result, evidence = apply_local_patch(section, {'U2'}, patch)
    expected = copy.deepcopy(before)
    expected['units'][1]['tex'] = patch['replacements'][0]['tex']
    assert result == expected
    assert section == before and patch == reply_before
    assert evidence['status'] == 'APPLIED_UNCHECKED'
    assert evidence['source_section_hash'] == digest(section)
    assert evidence['result_section_hash'] == digest(result)
    assert evidence['changed_unit_ids'] == ['U2']
    assert all(evidence[key] for key in ('unit_order_preserved', 'unit_identity_and_metadata_preserved',
        'non_target_units_preserved', 'non_target_calculations_preserved', 'old_uncertainties_preserved', 'old_calculation_limitations_preserved'))
    assert all(evidence[key] == 'NOT_RUN' for key in ('normalization', 'math_check', 'teacher_review'))
    result['metadata']['nested'][0]['source'] = 'changed'
    result['units'][1]['metadata']['source'].append(5)
    result['calculations'][1]['assumptions']['x'] = {}
    assert section == before


def test_multiple_targets_do_not_change_original_order(section, patch):
    patch['replacements'].insert(0, {'unit_id': 'U3', 'tex': '目标解释补充。'})
    result, evidence = apply_local_patch(section, ['U3', 'U2'], patch)
    assert [unit['id'] for unit in result['units']] == ['U1', 'U2', 'U3']
    assert evidence['allowed_unit_ids'] == ['U2', 'U3']
    assert result['units'][0] == section['units'][0]


@pytest.mark.parametrize('allowed', [[], ['FOREIGN'], ['U2', 'U2'], [None], 'U2', None, {'U2': True}])
def test_invalid_authorized_scope_is_rejected(section, patch, allowed):
    with pytest.raises(LocalPatchError):
        apply_local_patch(section, allowed, patch)


@pytest.mark.parametrize('mode', ['foreign', 'duplicate', 'missing', 'section'])
def test_replacement_mapping_must_exactly_match_scope(section, patch, mode):
    allowed = ['U2']
    if mode == 'foreign': patch['replacements'][0]['unit_id'] = 'U3'
    elif mode == 'duplicate': patch['replacements'].append(copy.deepcopy(patch['replacements'][0]))
    elif mode == 'missing': allowed.append('U3')
    else: patch['section_id'] = 'S99'
    before = copy.deepcopy(section)
    with pytest.raises(LocalPatchError): apply_local_patch(section, allowed, patch)
    assert section == before


@pytest.mark.parametrize('field', ['units', 'calculations', 'uncertainties', 'calculation_limitations', 'metadata', 'status'])
def test_full_fields_or_deletion_requests_are_not_sanitized(section, patch, field):
    patch[field] = []
    with pytest.raises(ValidationError): apply_local_patch(section, ['U2'], patch)


@pytest.mark.parametrize('field', ['id', 'kind', 'relates_to', 'metadata'])
def test_replacement_cannot_choose_identity_relation_or_metadata(section, patch, field):
    patch['replacements'][0][field] = 'changed'
    with pytest.raises(ValidationError): apply_local_patch(section, ['U2'], patch)


def test_empty_calculation_updates_cannot_delete_any_old_request(section, patch):
    patch.update(calculation_updates=[], calculation_additions=[])
    result, _ = apply_local_patch(section, ['U2'], patch)
    assert result['calculations'] == section['calculations']


def test_target_update_and_addition_keep_other_calculations_and_metadata(section, patch):
    section['calculations'][0]['metadata'] = {'audit': ['preserved']}
    patch.update(calculation_updates=[calculation()], calculation_additions=[calculation('C3')],
        uncertainties_append=['新增疑点'], calculation_limitations_append=['新增限制'])
    result, evidence = apply_local_patch(section, ['U2'], patch)
    assert len(result['calculations']) == 3
    assert result['calculations'][0] == calculation() | {'metadata': {'audit': ['preserved']}}
    assert result['calculations'][1] == section['calculations'][1]
    assert result['calculations'][2] == calculation('C3')
    assert result['uncertainties'] == section['uncertainties'] + ['新增疑点']
    assert result['calculation_limitations'] == section['calculation_limitations'] + ['新增限制']
    assert evidence['calculation_updates'] == ['C1'] and evidence['calculation_additions'] == ['C3']


@pytest.mark.parametrize('mode', ['foreign_unit', 'unknown_id', 'rebind', 'duplicate', 'implicit_id'])
def test_update_requires_existing_explicit_id_and_original_target_binding(section, patch, mode):
    request = calculation()
    allowed = ['U2']
    if mode == 'foreign_unit': request = calculation('C2', 'U3')
    elif mode == 'unknown_id': request['id'] = 'C99'
    elif mode == 'rebind':
        request['unit_id'] = 'U1'
        allowed.append('U1')
        patch['replacements'].append({'unit_id': 'U1', 'tex': section['units'][0]['tex']})
    elif mode == 'implicit_id':
        section['calculations'][0].pop('id')
        request['id'] = 'C001'
    patch['calculation_updates'] = [request, copy.deepcopy(request)] if mode == 'duplicate' else [request]
    with pytest.raises(LocalPatchError): apply_local_patch(section, allowed, patch)


@pytest.mark.parametrize('mode', ['old_id', 'new_duplicate', 'foreign_unit', 'implicit_collision'])
def test_additions_require_unique_id_and_target_binding(section, patch, mode):
    request = calculation('C3')
    if mode == 'old_id': request['id'] = 'C1'
    elif mode == 'foreign_unit': request['unit_id'] = 'U3'
    elif mode == 'implicit_collision':
        section['calculations'][0].pop('id')
        request['id'] = 'C001'
    patch['calculation_additions'] = [request, copy.deepcopy(request)] if mode == 'new_duplicate' else [request]
    with pytest.raises(LocalPatchError): apply_local_patch(section, ['U2'], patch)


@pytest.mark.parametrize('mode', ['extra', 'missing', 'unsupported', 'oversized', 'nonfinite', 'bad_id', 'bad_unit'])
def test_calculation_protocol_shape_and_byte_limits(section, patch, mode):
    request = calculation()
    if mode == 'extra': request['status'] = 'PASS'
    elif mode == 'missing': request.pop('assumptions')
    elif mode == 'unsupported': request['kind'] = 'python'
    elif mode == 'oversized': request['lhs'] = {'op': 'Symbol', 'name': 'x' * 65536}
    elif mode == 'nonfinite': request['rhs'] = {'op': 'Integer', 'value': float('nan')}
    elif mode == 'bad_id': request['id'] = []
    else: request['unit_id'] = []
    patch['calculation_updates'] = [request]
    with pytest.raises(LocalPatchError): apply_local_patch(section, ['U2'], patch)


def test_calculation_capacity_and_duplicate_existing_ids_block(section, patch):
    section['calculations'] = [calculation(f'C{i}') for i in range(100)]
    patch['calculation_additions'] = [calculation('EXTRA')]
    with pytest.raises(LocalPatchError, match='100-request'): apply_local_patch(section, ['U2'], patch)
    patch['calculation_additions'] = []
    section['calculations'][1]['id'] = section['calculations'][0]['id']
    with pytest.raises(LocalPatchError, match='ambiguous'): apply_local_patch(section, ['U2'], patch)


@pytest.mark.parametrize('body', ['', ' ', 'x' * 30001], ids=['empty', 'blank', 'oversized'])
def test_malformed_replacement_body_rejected(section, patch, body):
    patch['replacements'][0]['tex'] = body
    with pytest.raises(ValidationError): apply_local_patch(section, ['U2'], patch)


@pytest.mark.parametrize('field', ['uncertainties_append', 'calculation_limitations_append'])
def test_bad_append_notes_rejected_without_clearing_original(section, patch, field):
    patch[field] = [' ']
    with pytest.raises(ValidationError): apply_local_patch(section, ['U2'], patch)
    patch[field] = []
    result, _ = apply_local_patch(section, ['U2'], patch)
    assert result['uncertainties'] == section['uncertainties']
    assert result['calculation_limitations'] == section['calculation_limitations']


@pytest.mark.parametrize('body', [r'\section{Escalate}', r'\input{other.tex}', r'\newcommand{\evil}{x}'])
def test_global_document_edits_block(section, patch, body):
    patch['replacements'][0]['tex'] = body
    with pytest.raises(LocalPatchError): apply_local_patch(section, ['U2'], patch)


def test_absent_metadata_lists_remain_absent_when_patch_does_not_add(section, patch):
    for key in ('calculations', 'uncertainties', 'calculation_limitations'): section.pop(key)
    result, _ = apply_local_patch(section, ('U2',), LocalPatch.model_validate(patch))
    assert not {'calculations', 'uncertainties', 'calculation_limitations'} & result.keys()


def test_captured_s04_whole_response_and_foreign_replacement_stay_rejected():
    fixture = json.loads((Path(__file__).parent / 'fixtures/local_patch_ch01_s04.json').read_bytes())
    section, rejected = fixture['section'], fixture['rejected_full_section']
    original = copy.deepcopy(section)
    before, after = {u['id']: u for u in section['units']}, {u['id']: u for u in rejected['units']}
    assert [uid for uid in before if before[uid] != after[uid]] == ['S04.U03', 'S04.U04']
    assert [issue['unit_id'] for issue in fixture['issues']] == ['S04.U04']
    with pytest.raises(ValidationError): apply_local_patch(section, ['S04.U04'], rejected)
    # Even an attempted patch representation of both actual changed bodies is
    # rejected wholesale. Do not drop U03 then accept the remaining response.
    attempted = {'section_id': 'S04', 'replacements': [
        {'unit_id': uid, 'tex': after[uid]['tex']} for uid in ('S04.U03', 'S04.U04')]}
    with pytest.raises(LocalPatchError): apply_local_patch(section, ['S04.U04'], attempted)
    assert section == original


@pytest.mark.parametrize('expected, checker_status', [(2, 'PASS'), (3, 'FAIL')])
def test_actual_bounded_checker_not_patch_decides_calculation_truth(section, patch, expected, checker_status):
    section['calculations'] = [calculation()]
    section['uncertainties'] = []
    patch['calculation_updates'] = [calculation(expected=expected)]
    result, evidence = apply_local_patch(section, ['U2'], patch)
    assert evidence['status'] == 'APPLIED_UNCHECKED' and evidence['math_check'] == 'NOT_RUN'
    checked = check_math(result)
    assert checked['status'] == checker_status, checked
    if expected == 3:
        assert any(item['evidence_type'] == 'symbolic_check_failed' for item in checked['evidence'])
