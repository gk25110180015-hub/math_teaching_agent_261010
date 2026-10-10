"""Conservative detector regressions; no API, compiler, or production changes."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('attribution_candidate', ROOT / 'reports/iteration4/review-evidence-attribution.candidate.py')
CANDIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANDIDATE)


def unit(identity, tex):
    return {'id': identity, 'kind': 'proof', 'tex': tex, 'relates_to': None}


def review(evidence, target='S04.U05', severity='blocking'):
    return {'issues': [{'unit_id': target, 'severity': severity, 'message': '核对证明及依赖。', 'evidence': evidence}],
            'checked_unit_ids': [target], 'limitations': []}


def test_real_misattribution_identifies_supplied_prior_unit_without_changing_issue():
    captured = json.loads((ROOT / 'reports/iteration4/CH03-S04-round3-local-followup.json').read_text(encoding='utf-8'))
    original = captured['reviews'][0]['value']
    current = captured['versions']['local_normalized']['value']['units']
    source = captured['misattributed_proof']['actual_proof']
    before = copy.deepcopy(original)
    hits = CANDIDATE.detect_attribution_conflicts(original, current, [{'units': [unit('S02.U03', source)]}])
    assert len(hits) == 1
    assert hits[0]['target_unit_id'] == 'S04.U05'
    assert hits[0]['matches'][0]['source_unit_id'] == 'S02.U03'
    assert hits[0]['matches'][0]['source_owner'] == 'prior'
    assert '最后证明复合极限结论' in hits[0]['matches'][0]['anchor']
    assert original == before


def test_legal_cross_unit_dependency_critique_is_not_a_false_ownership_claim():
    theorem = '应用商的极限法则时必须保证分母极限为非零实数。'
    critique = review('先前 S02.U01：『' + theorem + '』；S04.U05 未核对分母极限非零，故错误使用该先修定理。')
    assert CANDIDATE.detect_attribution_conflicts(critique, [unit('S04.U05', '直接使用商法则。')],
               [{'units': [unit('S02.U01', theorem)]}]) == []


def test_absence_critique_does_not_need_a_matching_quote():
    assert CANDIDATE.detect_attribution_conflicts(review('当前证明未给出分母不为零的必要条件。'),
               [unit('S04.U05', '直接相除。')]) == []


@pytest.mark.parametrize('other', ['duplicate', 'target_contains', 'short', 'unprovided'])
def test_ambiguous_short_or_absent_source_cannot_establish_wrong_owner(other):
    phrase = '最后证明复合极限结论。按该结论的假设，取'
    target = unit('S04.U05', '另一个证明。')
    prior = [unit('S02.U03', phrase)]
    if other == 'duplicate':
        prior.append(unit('S03.U03', phrase))
    elif other == 'target_contains':
        target['tex'] = phrase
    elif other == 'short':
        phrase = 'x>0'
        prior[0]['tex'] = phrase
    elif other == 'unprovided':
        prior = []
    assert CANDIDATE.detect_attribution_conflicts(review('S04.U05：『' + phrase + '』'),
               [target], [{'units': prior}]) == []


@pytest.mark.parametrize('changed', [r'n \neq 0', r'n < 0', r'n_1 > 0'])
def test_math_symbols_and_indices_are_not_erased_to_make_a_match(changed):
    prefix = 'For every index satisfying the exact condition '
    evidence = review('S04.U05: "' + prefix + changed + ' the theorem applies."')
    source = prefix + 'n > 0 the theorem applies.'
    assert CANDIDATE.detect_attribution_conflicts(evidence, [unit('S04.U05', 'Different proof.')],
               [{'units': [unit('S02.U03', source)]}]) == []


def test_same_id_different_supplied_bodies_is_rejected_not_arbitrarily_chosen():
    with pytest.raises(ValueError, match='Ambiguous supplied unit identity'):
        CANDIDATE.detect_attribution_conflicts(review('没有直接引文。'), [unit('S04.U05', '新稿')],
                     [{'units': [unit('S04.U05', '旧稿')]}])
