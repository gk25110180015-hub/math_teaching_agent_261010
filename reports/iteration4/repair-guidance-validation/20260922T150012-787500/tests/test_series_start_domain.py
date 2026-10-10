"""Real, offline SymPy checks: convergence cannot validate an undefined first term."""
import pytest

from math_agent.mathcheck import _calculate


def integer(value):
    return {'op': 'Integer', 'value': value}


N = {'op': 'Symbol', 'name': 'n'}
LOG_N = {'op': 'log', 'args': [N]}


def op(name, *args):
    return {'op': name, 'args': list(args)}


def reciprocal(expression):
    return op('Pow', expression, integer(-1))


def request(term, start=1, *, expected=False, assumptions=None):
    return {'kind': 'series', 'assumptions': assumptions or {'n': {'integer': True, 'positive': True}},
            'term': term, 'variable': 'n', 'start': integer(start), 'end': {'op': 'Infinity'},
            'expected_convergent': expected}


@pytest.mark.unit
@pytest.mark.parametrize('term,start', [
    (reciprocal(op('Mul', N, LOG_N)), 1),
    (reciprocal(op('Add', N, integer(-1))), 1),
    (LOG_N, 0),
    (op('Mul', LOG_N, reciprocal(LOG_N)), 1),
    (op('Mul', op('Add', N, integer(-1)), reciprocal(op('Add', N, integer(-1)))), 1),
    (op('sqrt', op('Add', N, integer(-2))), 1),
])
def test_undefined_first_term_never_passes_tail_convergence(term, start):
    result = _calculate(request(term, start))
    assert result['status'] == 'FAIL', result
    assert result['evidence_type'] == 'series_term_undefined', result
    assert result['at_index'] == str(start)


@pytest.mark.unit
@pytest.mark.parametrize('term,start,expected', [
    (reciprocal(op('Mul', N, LOG_N)), 2, False),
    (reciprocal(op('Add', N, integer(-1))), 2, False),
    (reciprocal(N), 1, False),
    (op('Pow', N, integer(-2)), 1, True),
    (op('Mul', LOG_N, reciprocal(LOG_N)), 2, False),
    (op('sqrt', N), 1, False),
])
def test_defined_start_retains_the_convergence_result(term, start, expected):
    result = _calculate(request(term, start, expected=expected))
    assert result['status'] == 'PASS', result
    assert result['domain_scope'] == 'supported_tail_guards'
    assert result['evidence_type'] == 'symbolic_check_passed'


@pytest.mark.unit
def test_symbolic_unresolved_first_term_is_unknown():
    parameter = {'op': 'Symbol', 'name': 'a'}
    result = _calculate(request(reciprocal(op('Add', N, parameter)),
        assumptions={'n': {'integer': True, 'positive': True}, 'a': {'real': True}}))
    assert result['status'] == 'UNKNOWN', result
    assert result['domain_scope'] == 'supported_tail_guards'


@pytest.mark.unit
def test_finite_first_term_does_not_hide_a_later_pole():
    result = _calculate(request(reciprocal(op('Add', N, integer(-2)))))
    assert result['status'] in {'UNKNOWN', 'FAIL'}, result
    assert result['evidence_type'] != 'symbolic_check_passed'
    assert result['domain_scope'] == 'supported_tail_guards'


@pytest.mark.unit
def test_cancellation_must_not_hide_a_later_pole():
    shifted = op('Add', N, integer(-2))
    result = _calculate(request(op('Mul', shifted, reciprocal(shifted))))
    assert result['status'] in {'UNKNOWN', 'FAIL'}, result
    assert result['evidence_type'] != 'symbolic_check_passed'


@pytest.mark.unit
def test_domain_that_fails_later_is_not_approved_from_first_term():
    result = _calculate(request(op('sqrt', op('Add', integer(2), op('Mul', integer(-1), N)))))
    assert result['status'] in {'UNKNOWN', 'FAIL'}, result
    assert result['evidence_type'] != 'symbolic_check_passed'


@pytest.mark.unit
def test_noninteger_series_start_is_not_silently_checked():
    payload = request(reciprocal(N))
    payload['start'] = {'op': 'Rational', 'p': 1, 'q': 2}
    result = _calculate(payload)
    assert result['status'] == 'UNKNOWN', result
