"""Build a reviewable patch beside reports without changing production source."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

root = Path(__file__).resolve().parents[2]
source = root / 'src/math_agent/mathcheck.py'
original = source.read_text(encoding='utf-8')
candidate = original


def replace_once(before, after):
    global candidate
    assert candidate.count(before) == 1, before
    candidate = candidate.replace(before, after, 1)


replace_once('    unresolved_domains = []\n', '    unresolved_domains = []\n    series_domain_guards = []\n')
replace_once("            return functions[op](*args)\n", """            if kind == 'series':
                if op == 'log':
                    series_domain_guards.append(('positive', args[0], 'log'))
                elif op == 'sqrt':
                    series_domain_guards.append(('nonnegative', args[0], 'sqrt'))
                elif op == 'tan':
                    series_domain_guards.append(('nonzero', sp.cos(args[0]), 'tan'))
            return functions[op](*args)
""")
replace_once("            return sp.Pow(*args)\n", """            if kind == 'series' and args[1].is_negative is True:
                # Keep the original denominator even when SymPy later cancels it.
                series_domain_guards.append(('nonzero', args[0], 'negative_power'))
            return sp.Pow(*args)
""")
replace_once("        actual = sp.Sum(expression(request['term']), (variable, expression(request['start']), expression(request['end']))).is_convergent()\n", """        term = expression(request['term'])
        term_guards = list(series_domain_guards)
        start, end = expression(request['start']), expression(request['end'])
        scope = {'domain_scope': 'supported_tail_guards',
                 'limitations': ['以起点加非负整数代入，检查已保留的受支持运算定义域约束；不是通用定义域证明器。']}
        base.update(scope)
        if start.is_integer is not True or start.is_finite is not True or start.free_symbols:
            return {**base, 'status': 'UNKNOWN', 'evidence_type': 'not_checked',
                    'message': '级数首项定义域检查需要确定的有限整数起点。'}
        if end.is_finite is True and (end < start) is sp.S.true:
            return {**base, 'status': 'UNKNOWN', 'evidence_type': 'not_checked',
                    'message': '终点小于起点，未按非空递增级数检查首项。'}
        unknown_guards = []
        for property_name, guard, operation in term_guards:
            value = guard.subs(variable, start)
            property_value = getattr(value, 'is_' + property_name)
            location = {'at_index': str(start), 'variable': str(variable),
                        'expression': str(guard)[:500], 'operation': operation,
                        'required_property': property_name}
            if property_value is False or value.has(sp.nan, sp.zoo, sp.oo, -sp.oo):
                return {**base, **location, 'status': 'FAIL',
                        'evidence_type': 'series_term_undefined',
                        'message': '指定求和起点项不在原表达式定义域内；尾部收敛性不能使该级数合法。'}
            if property_value is not True:
                unknown_guards.append(location)
        if unknown_guards:
            return {**base, 'status': 'UNKNOWN', 'evidence_type': 'not_checked',
                    'domain_requirements': unknown_guards,
                    'message': '指定求和起点项仍有未决定的定义域条件，不能仅凭尾部收敛性通过。'}
        first_term = term.subs(variable, start)
        if first_term.has(sp.nan, sp.zoo, sp.oo, -sp.oo) or first_term.is_finite is False or first_term.is_real is False:
            return {**base, 'at_index': str(start), 'variable': str(variable),
                    'status': 'FAIL', 'evidence_type': 'series_term_undefined',
                    'message': '指定求和起点项不是有定义的有限实数；不能只核对尾部收敛性。'}
        if first_term.is_finite is not True or first_term.is_real is not True:
            return {**base, 'status': 'UNKNOWN', 'evidence_type': 'not_checked',
                    'message': '无法确认指定求和起点项为有定义的有限实数。'}
        tail_index = sp.Dummy('series_offset', integer=True, nonnegative=True)
        tail_requirements = []
        for property_name, guard, operation in term_guards:
            tail_guard = guard.subs(variable, start + tail_index)
            if getattr(tail_guard, 'is_' + property_name) is not True:
                tail_requirements.append({'expression': str(guard)[:500],
                    'operation': operation, 'required_property': property_name})
        tail_term = term.subs(variable, start + tail_index)
        if tail_term.is_real is not True or tail_term.is_finite is not True:
            tail_requirements.append({'expression': str(term)[:500],
                'required_property': 'finite_real'})
        if tail_requirements:
            return {**base, 'status': 'UNKNOWN', 'evidence_type': 'not_checked',
                    'domain_requirements': tail_requirements,
                    'message': '首项可定义，但尚不能确认所有后续整数项均满足原表达式定义域；未将尾部收敛结论记为通过。'}
        actual = sp.Sum(term, (variable, start, end)).is_convergent()
""")

ast_candidate = candidate
replace_once('def _static_checks(units: list[dict]) -> list[dict]:\n    issues = []\n',
             'def _static_checks(units: list[dict]) -> list[dict]:\n    from .series_domain_text import series_first_term_review\n    issues = series_first_term_review(units)\n')
directory = Path(__file__).resolve().parent / '待合并'
directory.mkdir(exist_ok=True)
for name in ('mathcheck-series-domain.py', 'series-domain.patch', 'series-domain-source-hashes.json'):
    prior = directory / name
    if prior.exists():
        digest = hashlib.sha256(prior.read_bytes()).hexdigest()[:12]
        preserved = prior.with_name(prior.stem + '-' + digest + prior.suffix)
        if not preserved.exists():
            shutil.copy2(prior, preserved)
(directory / 'mathcheck-series-domain.py').write_text(candidate, encoding='utf-8')
(directory / 'series-domain.patch').write_text(''.join(difflib.unified_diff(
    original.splitlines(keepends=True), ast_candidate.splitlines(keepends=True),
    fromfile='a/src/math_agent/mathcheck.py', tofile='b/src/math_agent/mathcheck.py')), encoding='utf-8')
text_scanner = (directory / 'series_domain_text.py').read_text(encoding='utf-8')
(directory / 'series-text-domain.patch').write_text(''.join(difflib.unified_diff(
    ast_candidate.splitlines(keepends=True), candidate.splitlines(keepends=True),
    fromfile='a/src/math_agent/mathcheck.py', tofile='b/src/math_agent/mathcheck.py')) +
    ''.join(difflib.unified_diff([], text_scanner.splitlines(keepends=True),
    fromfile='/dev/null', tofile='b/src/math_agent/series_domain_text.py')), encoding='utf-8')
(directory / 'series-domain-source-hashes.json').write_text(json.dumps({
    'source': str(source), 'original_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'candidate_sha256': hashlib.sha256((directory / 'mathcheck-series-domain.py').read_bytes()).hexdigest(),
    'text_scanner_sha256': hashlib.sha256((directory / 'series_domain_text.py').read_bytes()).hexdigest(),
    'production_modified': False,
}, indent=2), encoding='utf-8')
print(json.dumps({'candidate': str(directory / 'mathcheck-series-domain.py'), 'production_modified': False}, ensure_ascii=False))
