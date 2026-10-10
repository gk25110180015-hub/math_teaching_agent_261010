"""Exercise deployed domain guards through the real isolated SymPy process."""
import pytest

from math_agent.mathcheck import check_math


@pytest.mark.integration
@pytest.mark.parametrize('start,expected_status,evidence_type', [
    (1, 'FAIL', 'series_term_undefined'),
    (2, 'PASS', 'symbolic_check_passed'),
])
def test_logarithmic_series_domain_crosses_worker_boundary(start, expected_status, evidence_type):
    n = {'op': 'Symbol', 'name': 'n'}
    request = {
        'id': 'C-domain', 'unit_id': 'S1.U1', 'kind': 'series',
        'assumptions': {'n': {'integer': True, 'positive': True}},
        'term': {'op': 'Pow', 'args': [
            {'op': 'Mul', 'args': [n, {'op': 'log', 'args': [n]}]},
            {'op': 'Integer', 'value': -1}]},
        'variable': 'n', 'start': {'op': 'Integer', 'value': start},
        'end': {'op': 'Infinity'}, 'expected_convergent': False,
    }
    result = check_math({'units': [{'id': 'S1.U1', 'tex': '核对指定起点的对数级数。'}],
                         'calculations': [request]})
    assert result['status'] == expected_status, result
    evidence = result['evidence'][0]
    assert evidence['status'] == expected_status, evidence
    assert evidence['evidence_type'] == evidence_type, evidence
    assert evidence['domain_scope'] == 'supported_tail_guards'
    assert evidence['unit_id'] == 'S1.U1'
    if start == 1:
        assert evidence['at_index'] == '1'
        assert any(issue['rule_id'] == 'SYMBOLIC_COUNTERCHECK_FAILED'
                   and issue['severity'] == 'blocking'
                   and issue['location']['unit_id'] == 'S1.U1'
                   for issue in result['issues'])
    else:
        assert not result['issues'], result
