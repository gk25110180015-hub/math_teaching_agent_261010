"""Narrow symbolic checks using a JSON AST, never Python evaluation or TeX execution.

Calculation protocol:
  assumptions: {symbol_name: {real/positive/integer/...: bool}}
  equivalence: lhs, rhs
  derivative: expression, variable, expected
  limit: expression, variable, point, direction (+/-/+-), expected
  series: term, variable, start, end, expected_convergent: bool
  numeric_spotcheck: lhs, rhs, points: [{symbol_name: finite number}]
AST: {op: Integer, value: int}, {op: Rational, p:int, q:int},
     {op: Symbol, name:str}, {op: Infinity}, or {op, args:[AST,...]}.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def math_child_environment() -> dict[str, str]:
    env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR', 'SystemDrive', 'LANG') if k in os.environ}
    env.update({'PATH': str(Path(sys.executable).parent),
                'PYTHONPATH': str(Path(__file__).resolve().parent.parent),
                'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8'})
    return env


def _issue(rule, message, severity='review', **location):
    return {'rule_id': rule, 'severity': severity, 'message': message,
            'location': location, 'resolution_status': 'open'}


def _static_checks(units: list[dict]) -> list[dict]:
    issues = []
    for unit in units:
        tex = unit.get('tex', unit.get('raw_tex', ''))
        plain = re.sub(r'\s+', '', tex)
        # Narrow, teacher-authored error fixtures; no claim of a universal theorem prover.
        zero_term = re.search(r'(?:通项|a_n|terms).{0,24}(?:趋于?零|趋于?0|tozero|\\to0)', plain, re.I)
        false_conclusion = re.search(r'(?:所以|因此|故|therefore|hence).{0,16}(?:级数收敛|seriesconverges)', plain, re.I)
        negated = re.search(r'(?:不能|并不|不代表|不足|not|doesnot).{0,12}(?:收敛|converg|推出|说明)', plain, re.I)
        other_criterion = re.search(r'(?:交错|交替|莱布尼茨|Leibniz|比较判别|积分判别|比值判别|根值判别)', plain, re.I)
        if zero_term and false_conclusion and not negated and not other_criterion:
            issues.append(_issue('ZERO_TERM_NOT_SUFFICIENT', '通项趋零只是级数收敛的必要条件，不能据此推出收敛。',
                                 'blocking', unit_id=unit.get('id')))
        if '极限' in plain and '定义' in plain:
            if re.search(r'(?:存在|\\exists)\$?\\(?:varepsilon|epsilon)', plain):
                issues.append(_issue('LIMIT_QUANTIFIER_REVIEW', '极限定义的 epsilon 量词疑似使用存在量词，需核对任意性与量词顺序。',
                                     unit_id=unit.get('id')))
            if re.search(r'(?:存在|\\exists)\$?n>N', plain):
                issues.append(_issue('TAIL_QUANTIFIER_REVIEW', '极限定义疑似只要求存在尾项；需核对是否对所有 n>N 成立。',
                                     unit_id=unit.get('id')))
        if re.search(r'(?:所有|任意)(?:实数|实变量).{0,20}\\(?:log|ln)', plain):
            if not re.search(r'(?:x>0|x\\gt0|正实数)', plain):
                issues.append(_issue('LOG_DOMAIN_REVIEW', '实对数须明确正实数定义域；“所有实数”范围疑似不当。',
                                     unit_id=unit.get('id')))
    return issues


def check_math(section: dict) -> dict:
    issues = _static_checks(section.get('units', []))
    unit_ids = {u.get('id') for u in section.get('units', []) if isinstance(u.get('id'), str)}
    result = {'schema_version': 1, 'status': 'PASS', 'issues': issues, 'evidence': [],
              'coverage': [u.get('id') for u in section.get('units', [])],
              'limitations': ['只复算显式请求的受支持表达式，并做少量已知错误模式检查；不证明整份讲义正确。',
                              '数值抽查成功不是一般性证明；无法决定的表达式明确标记 UNKNOWN。']}
    calculations = section.get('calculations', [])
    result['limitations'].extend(str(x)[:1000] for x in section.get('calculation_limitations',[]))
    if not isinstance(calculations, list) or len(calculations) > 100:
        result['issues'].append(_issue('CALCULATION_LIMIT', '核算请求必须是最多 100 项的列表。', 'blocking'))
        calculations = []
    for uncertainty in section.get('uncertainties', []):
        result['issues'].append(_issue('DECLARED_MATH_UNCERTAINTY', str(uncertainty)[:1000]))
    if not calculations:
        result['evidence'].append({'evidence_type': 'not_checked', 'status': 'NOT_RUN',
                                  'message': '没有结构化复算请求，尚未执行 SymPy 数学核算。'})
    started = time.monotonic()
    for index, calculation in enumerate(calculations):
        calc_id = calculation.get('id', f'C{index + 1:03d}') if isinstance(calculation, dict) else f'C{index + 1:03d}'
        location = {'calculation_id': calc_id}
        if isinstance(calculation, dict) and 'unit_id' in calculation:
            unit_id = calculation['unit_id']
            if not isinstance(unit_id, str) or unit_id not in unit_ids:
                # Retain the requested ID but never target a nonexistent source unit for repair.
                location['requested_unit_id'] = unit_id
                message = '核算 unit_id 必须指向当前 section.units 中真实存在的单元。'
                result['issues'].append(_issue('CALCULATION_UNIT_BINDING', message, 'blocking', **location))
                result['evidence'].append({'status':'NOT_RUN','evidence_type':'not_checked','message':message,**location})
                continue
            location['unit_id'] = unit_id
        if time.monotonic() - started > 60:
            message = '本节数学复算已达 60 秒预算，本项未执行。'
            result['issues'].append(_issue('MATH_TOTAL_TIMEOUT', message, **location))
            result['evidence'].append({'status':'NOT_RUN','evidence_type':'not_checked','message':message,**location})
            continue
        try:
            payload = json.dumps(calculation, ensure_ascii=False, allow_nan=False).encode('utf-8')
        except (TypeError, ValueError, UnicodeError):
            message = '核算请求无法编码为受限 JSON。'
            result['issues'].append(_issue('MATH_INPUT_INVALID', message, 'blocking', **location))
            result['evidence'].append({'status':'NOT_RUN','evidence_type':'not_checked','message':message,**location})
            continue
        if len(payload) > 65536:
            message = '单个复算 JSON 超过 64 KiB。'
            result['issues'].append(_issue('MATH_INPUT_LIMIT', message, 'blocking', **location))
            result['evidence'].append({'status':'NOT_RUN','evidence_type':'not_checked','message':message,**location})
            continue
        try:
            process = subprocess.Popen([sys.executable, '-m', 'math_agent.mathcheck', '--child'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=math_child_environment(), shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                start_new_session=os.name != 'nt')
            stdout, stderr = process.communicate(payload, timeout=8)
            if process.returncode:
                raise ValueError('受限数学子进程失败。')
            evidence = json.loads(stdout)
            if not isinstance(evidence, dict) or evidence.get('status') not in {'PASS','FAIL','UNKNOWN','NOT_RUN'} or not isinstance(evidence.get('evidence_type'), str):
                raise ValueError('数学子进程未返回有效证据。')
        except subprocess.TimeoutExpired:
            from .compiler import terminate_tree
            terminate_tree(process)
            evidence = {'status': 'UNKNOWN', 'evidence_type': 'not_checked', 'message': '数学子进程超时，已终止所属进程树。'}
        except (ValueError, OSError) as exc:
            evidence = {'status': 'UNKNOWN', 'evidence_type': 'not_checked', 'message': str(exc)}
        evidence.update(location)
        result['evidence'].append(evidence)
        if evidence['status'] == 'FAIL':
            result['issues'].append(_issue('SYMBOLIC_COUNTERCHECK_FAILED', evidence.get('message', '复算与声明不一致。'),
                                         'blocking', **location))
        elif evidence['status'] != 'PASS':
            result['issues'].append(_issue('MATH_CHECK_UNKNOWN', evidence.get('message', '符号核算无法决定。'),
                                         **location))
        elif evidence['evidence_type'] == 'numeric_spotcheck_passed':
            # A successful sample limits tool evidence; it is not itself a body defect.
            # Keep NEEDS_REVIEW below, and let substantive reviewer issues gate repair.
            result['issues'].append(_issue('NUMERIC_IS_NOT_PROOF', '只通过指定点数值抽查，不能据此视为一般性证明。',
                                         'warning', **location))
    if any(i['severity'] == 'blocking' for i in result['issues']):
        result['status'] = 'FAIL'
    elif result['issues'] or not calculations:
        result['status'] = 'NEEDS_REVIEW'
    return result


def _calculate(request: dict) -> dict:
    import sympy as sp

    if not isinstance(request, dict):
        raise ValueError('核算必须是 JSON 对象。')
    assumptions = request.get('assumptions')
    if not isinstance(assumptions, dict) or len(assumptions) > 20:
        raise ValueError('必须显式提供 assumptions（可为空）。')
    allowed_assumptions = {'real', 'positive', 'negative', 'nonnegative', 'nonpositive', 'integer', 'nonzero', 'finite', 'rational'}
    symbols = {}
    for name, flags in assumptions.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,30}', name):
            raise ValueError('非法符号名称。')
        if not isinstance(flags, dict) or set(flags) - allowed_assumptions or any(type(v) is not bool for v in flags.values()):
            raise ValueError('假设只允许白名单布尔字段。')
        symbols[name] = sp.Symbol(name, **flags)
    nodes = 0
    unresolved_domains = []
    series_domain_guards = []
    functions = {'sin': sp.sin, 'cos': sp.cos, 'tan': sp.tan, 'exp': sp.exp, 'log': sp.log, 'sqrt': sp.sqrt, 'Abs': sp.Abs}

    def integer(value):
        if type(value) is not int or abs(value) > 1_000_000_000:
            raise ValueError('Integer 必须是绝对值不超过 10^9 的 JSON 整数。')
        return sp.Integer(value)

    def expression(node, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 256 or depth > 20:
            raise ValueError('表达式超过 256 节点或 20 层深度。')
        if not isinstance(node, dict) or not isinstance(node.get('op'), str):
            raise ValueError('只接受受限表达式 JSON 树；不解析字符串代码。')
        op = node['op']
        if op == 'Integer' and set(node) == {'op', 'value'}:
            return integer(node['value'])
        if op == 'Rational' and set(node) == {'op', 'p', 'q'}:
            p, q = integer(node['p']), integer(node['q'])
            if q == 0:
                raise ValueError('Rational 分母不能为零。')
            return sp.Rational(p, q)
        if op == 'Symbol' and set(node) == {'op', 'name'}:
            if node['name'] not in symbols:
                raise ValueError('所有变量必须在 assumptions 中声明。')
            return symbols[node['name']]
        if op == 'Infinity' and set(node) == {'op'}:
            return sp.oo
        if op not in {'Add', 'Mul', 'Pow', *functions} or set(node) != {'op', 'args'}:
            raise ValueError('未列入白名单的表达式操作。')
        if not isinstance(node['args'], list) or len(node['args']) > 16:
            raise ValueError('表达式参数必须是最多 16 项的数组。')
        args = [expression(arg, depth + 1) for arg in node['args']]
        if op in functions:
            if len(args) != 1:
                raise ValueError('初等函数只接受一个参数。')
            if op == 'log' and args[0].is_positive is not True:
                unresolved_domains.append(f'实对数参数须为正：{args[0]} > 0')
            if op == 'sqrt' and request.get('kind') == 'derivative' and args[0].is_positive is not True:
                unresolved_domains.append(f'平方根求导需单独核对零点/定义域边界：{args[0]} > 0')
            if kind == 'series':
                if op == 'log':
                    series_domain_guards.append(('positive', args[0], 'log'))
                elif op == 'sqrt':
                    series_domain_guards.append(('nonnegative', args[0], 'sqrt'))
                elif op == 'tan':
                    series_domain_guards.append(('nonzero', sp.cos(args[0]), 'tan'))
            return functions[op](*args)
        if op == 'Pow':
            if len(args) != 2 or (args[1].is_number and (abs(args[1]) > 100) is sp.S.true):
                raise ValueError('幂指数超出受限预算。')
            if args[1].is_negative is True and args[0].is_nonzero is not True:
                unresolved_domains.append(f'负指数底数须非零：{args[0]} != 0')
            if kind == 'series' and args[1].is_negative is True:
                # Keep the original denominator even when SymPy later cancels it.
                series_domain_guards.append(('nonzero', args[0], 'negative_power'))
            return sp.Pow(*args)
        if not args:
            raise ValueError('加法/乘法至少需要一个参数。')
        return (sp.Add if op == 'Add' else sp.Mul)(*args)

    kind = request.get('kind')
    common = {'id', 'unit_id', 'kind', 'assumptions'}
    fields = {
        'equivalence': {'lhs','rhs'}, 'derivative': {'expression','variable','expected'},
        'limit': {'expression','variable','point','direction','expected'},
        'series': {'term','variable','start','end','expected_convergent'},
        'numeric_spotcheck': {'lhs','rhs','points'},
    }
    if kind not in fields or set(request) - common - fields.get(kind, set()):
        raise ValueError('核算类型或字段不受支持。')
    base = {'kind': kind, 'assumptions': assumptions, 'tool': 'SymPy', 'tool_version': sp.__version__}

    def compare(actual, expected):
        if unresolved_domains and kind in {'equivalence', 'derivative'}:
            return {**base, 'status':'UNKNOWN', 'evidence_type':'not_checked',
                    'domain_requirements': sorted(set(unresolved_domains)),
                    'message':'表达式简化前存在未声明的定义域条件，不能仅凭简化结果视为正确。'}
        if actual == expected and actual not in (sp.nan, sp.zoo):
            return {**base, 'status':'PASS', 'evidence_type':'symbolic_check_passed',
                    'result':str(actual)[:1000], 'message':'在声明假设下符号结果与预期完全一致。'}
        difference = sp.simplify(actual - expected)
        if difference == 0 or difference.is_zero is True:
            return {**base, 'status':'PASS', 'evidence_type':'symbolic_check_passed',
                    'result':str(actual)[:1000], 'message':'在声明假设下符号差为零。'}
        if difference.is_zero is False:
            return {**base, 'status':'FAIL', 'evidence_type':'symbolic_check_failed',
                    'result':str(actual)[:1000], 'message':'在声明假设下符号结果与预期不一致。'}
        return {**base, 'status':'UNKNOWN', 'evidence_type':'not_checked',
                'result':str(actual)[:1000], 'message':'符号差的零值性未知；不视为正确。'}

    if kind == 'equivalence':
        return compare(expression(request['lhs']), expression(request['rhs']))
    if kind == 'numeric_spotcheck':
        lhs, rhs = expression(request['lhs']), expression(request['rhs'])
        points = request.get('points')
        if not isinstance(points, list) or not 1 <= len(points) <= 20:
            raise ValueError('数值抽查需要 1..20 个明确的点。')
        for point in points:
            if not isinstance(point, dict) or set(point) != set(symbols):
                raise ValueError('每个数值点必须覆盖声明的全部变量。')
            substitutions = {}
            for name, value in point.items():
                if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e9:
                    raise ValueError('数值点必须是有界有限数。')
                candidate = sp.Integer(value) if type(value) is int else sp.Float(value)
                for assumption, required in assumptions[name].items():
                    actual_property = getattr(candidate, 'is_' + assumption)
                    if actual_property is not required:
                        raise ValueError('数值点不满足已声明的变量假设。')
                substitutions[symbols[name]] = value
            difference = (lhs-rhs).subs(substitutions).evalf(20)
            if not difference.is_number or difference.is_finite is not True:
                return {**base,'status':'UNKNOWN','evidence_type':'not_checked','message':'抽查点不在可计算定义域。'}
            if abs(complex(difference)) > 1e-9:
                return {**base,'status':'FAIL','evidence_type':'numeric_spotcheck_failed','message':'指定数值点发现反例。'}
        return {**base,'status':'PASS','evidence_type':'numeric_spotcheck_passed','point_count':len(points),
                'message':'仅在指定点数值一致，不是一般性证明。'}
    variable = symbols.get(request.get('variable'))
    if variable is None:
        raise ValueError('核算变量没有显式假设声明。')
    if kind == 'derivative':
        return compare(sp.diff(expression(request['expression']), variable), expression(request['expected']))
    if kind == 'limit':
        direction = request.get('direction')
        if direction not in {'+', '-', '+-'}:
            raise ValueError('limit 必须明确 direction 为 +、- 或 +-。')
        actual = sp.limit(expression(request['expression']), variable, expression(request['point']), dir=direction)
        return compare(actual, expression(request['expected']))
    if kind == 'series':
        expected = request.get('expected_convergent')
        if type(expected) is not bool:
            raise ValueError('级数 expected_convergent 必须是布尔值。')
        term = expression(request['term'])
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
        if actual not in (sp.S.true, sp.S.false, True, False):
            return {**base,'status':'UNKNOWN','evidence_type':'not_checked','message':'SymPy 无法决定此级数收敛性。'}
        passed = bool(actual) == expected
        return {**base,'status':'PASS' if passed else 'FAIL',
                'evidence_type':'symbolic_check_passed' if passed else 'symbolic_check_failed',
                'result':bool(actual),'message':'级数收敛性核算与声明一致。' if passed else '级数收敛性核算与声明矛盾。'}
    raise ValueError('Unsupported calculation')


if __name__ == '__main__' and '--child' in sys.argv:
    try:
        payload = sys.stdin.buffer.read(65537)
        if len(payload) > 65536:
            raise ValueError('Math input too large')
        response = _calculate(json.loads(payload))
    except Exception as exc:
        response = {'status':'UNKNOWN','evidence_type':'not_checked','message':type(exc).__name__ + ': ' + str(exc)[:500]}
    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
