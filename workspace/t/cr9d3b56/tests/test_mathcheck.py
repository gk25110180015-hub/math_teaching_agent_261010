import pytest
from math_agent.mathcheck import check_math

X = {'op': 'Symbol', 'name': 'x'}
N = {'op': 'Symbol', 'name': 'n'}
def integer(n): return {'op': 'Integer', 'value': n}
def power(a,b): return {'op':'Pow','args':[a,b]}
def section(calculations=None, text='设实变量，核对如下恒等式。'):
    return {'section_id':'S01','units':[{'id':'U01','kind':'theorem','tex':text}], 'calculations':calculations or []}


@pytest.mark.unit
def test_t23_zero_term_is_not_series_convergence():
    result = check_math(section(text='因为级数通项趋于零，所以级数收敛。'))
    assert result['status'] == 'FAIL'
    assert any(i['rule_id']=='ZERO_TERM_NOT_SUFFICIENT' for i in result['issues'])


@pytest.mark.unit
def test_alternating_series_criterion_is_not_falsely_rejected():
    result = check_math(section(text='交错级数的正项单调递减且通项趋于零，因此级数收敛（莱布尼茨判别）。'))
    assert not any(i['rule_id']=='ZERO_TERM_NOT_SUFFICIENT' for i in result['issues'])
    assert result['status']=='NEEDS_REVIEW'  # No structured symbolic calculation was requested.


@pytest.mark.unit
def test_t24_quantifier_and_log_domain_are_reviewed():
    for text in [r'数列极限定义：存在 $\varepsilon>0$，对每个 $N$，存在 $n>N$ 满足条件。',
                 r'对所有实数 $x$，$\log x$ 都有定义。']:
        result = check_math(section(text=text))
        assert result['status'] in {'FAIL','NEEDS_REVIEW'} and result['issues']


@pytest.mark.unit
def test_symbolic_derivative_and_limit():
    result = check_math(section([
        {'id':'C01','kind':'derivative','expression':power(X,integer(2)), 'variable':'x',
         'expected':{'op':'Mul','args':[integer(2),X]},'assumptions':{'x':{'real':True}}},
        {'id':'C02','kind':'limit','expression':{'op':'Mul','args':[{'op':'sin','args':[X]},power(X,integer(-1))]},
         'variable':'x','point':integer(0),'direction':'+-','expected':integer(1),'assumptions':{'x':{'real':True}}},
    ]))
    assert result['status']=='PASS', result
    assert all(e['evidence_type']=='symbolic_check_passed' for e in result['evidence'])


@pytest.mark.unit
def test_t25_missing_assumption_does_not_become_true():
    result = check_math(section([{'kind':'equivalence','lhs':{'op':'sqrt','args':[power(X,integer(2))]},
                                 'rhs':X,'assumptions':{'x':{}}}]))
    assert result['status'] in {'FAIL','NEEDS_REVIEW'}
    assert result['evidence'][0]['evidence_type'] != 'symbolic_check_passed'


@pytest.mark.unit
def test_t24_cancelling_denominator_does_not_erase_domain():
    result = check_math(section([{'kind':'equivalence','lhs':{'op':'Mul','args':[X,power(X,integer(-1))]},
                                 'rhs':integer(1),'assumptions':{'x':{'real':True}}}]))
    assert result['status']=='NEEDS_REVIEW'
    assert result['evidence'][0]['domain_requirements']


@pytest.mark.unit
def test_series_harmonic_fails_claim_of_convergence():
    result = check_math(section([{'kind':'series','term':power(N,integer(-1)),'variable':'n',
        'start':integer(1),'end':{'op':'Infinity'},'expected_convergent':True,
        'assumptions':{'n':{'integer':True,'positive':True}}}]))
    assert result['status']=='FAIL',result


@pytest.mark.unit
def test_t26_numeric_success_stays_numeric():
    result = check_math(section([{'kind':'numeric_spotcheck','lhs':X,'rhs':X,
        'points':[{'x':1},{'x':2}], 'assumptions':{'x':{'real':True}}}]))
    assert result['status']=='NEEDS_REVIEW'
    assert result['evidence'][0]['evidence_type']=='numeric_spotcheck_passed'


@pytest.mark.security
def test_no_python_eval_or_unbounded_ast(tmp_path):
    payloads = [{'op':'__import__','args':['os']},'__import__("os").system("whoami")',
                power(integer(99),integer(999999))]
    for payload in payloads:
        result=check_math(section([{'kind':'equivalence','lhs':payload,'rhs':integer(1),'assumptions':{}}]))
        assert result['status'] in {'FAIL','NEEDS_REVIEW'}
        assert not any(e['evidence_type']=='symbolic_check_passed' for e in result['evidence'])


@pytest.mark.security
def test_math_subprocess_env_has_no_api_secret(monkeypatch):
    from math_agent.mathcheck import math_child_environment
    monkeypatch.setenv('MATH_AGENT_API_KEY','synthetic-value-never-child')
    env = math_child_environment()
    assert 'MATH_AGENT_API_KEY' not in env
    assert 'synthetic-value-never-child' not in str(env)
