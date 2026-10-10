"""Verify narrowly scoped calculation repairs without rewriting correct prose.

This admits new checked evidence, never a mathematical verdict or publication.
The original body, doubts, failed requests and reports remain caller-owned.
"""
import copy

from .mathcheck import check_math
from .util import digest


_EXPRESSION_FIELDS = {'equivalence': 'lhs', 'derivative': 'expression',
                      'limit': 'expression', 'series': 'term'}
_FAILURE_STATUS = {'SYMBOLIC_COUNTERCHECK_FAILED': 'FAIL', 'MATH_CHECK_UNKNOWN': 'UNKNOWN'}


def verify_independent_calculation_repair(before, after, repair_issues, tool_checks):
    """Return actual scoped verification evidence, or None without authorizing it.

    Each changed request must already have a matching independent tool failure.
    Only its expression can change; expected answers, assumptions and bindings
    stay fixed.  A bounded symbolic check must then pass for every changed item.
    """
    try:
        if not all(isinstance(value, dict) for value in (before, after, tool_checks)):
            return None
        if ({key: value for key, value in before.items() if key != 'calculations'}
                != {key: value for key, value in after.items() if key != 'calculations'}):
            return None
        units = before['units']
        if not isinstance(units, list) or not units:
            return None
        unit_ids = [unit['id'] for unit in units]
        if (not all(isinstance(key, str) and key for key in unit_ids)
                or len(unit_ids) != len(set(unit_ids))):
            return None
        originals, replacements = before['calculations'], after['calculations']
        if (not isinstance(originals, list) or not isinstance(replacements, list)
                or not 1 <= len(originals) <= 100 or len(originals) != len(replacements)
                or not all(isinstance(item, dict) for item in originals + replacements)):
            return None
        ids = [item['id'] for item in originals]
        if (not all(isinstance(key, str) and key for key in ids) or len(ids) != len(set(ids))
                or ids != [item['id'] for item in replacements]):
            return None
        changed = [(original, replacement) for original, replacement in zip(originals, replacements)
                   if original != replacement]
        if not changed or not isinstance(repair_issues, list):
            return None
        tool_issues, evidence = tool_checks['issues'], tool_checks['evidence']
        if not isinstance(tool_issues, list) or not isinstance(evidence, list):
            return None
        matched, old_evidence = [], []
        for original, replacement in changed:
            unit_id, calculation_id = original['unit_id'], original['id']
            expression_field = _EXPRESSION_FIELDS.get(original['kind'])
            if (unit_id not in unit_ids or expression_field is None
                    or expression_field not in original or expression_field not in replacement
                    or {key: value for key, value in original.items() if key != expression_field}
                    != {key: value for key, value in replacement.items() if key != expression_field}):
                return None
            # Match the complete issue, not merely a model-supplied calculation
            # ID.  Ordinary warnings cannot create a tool-repair permission.
            sources = [issue for issue in repair_issues if isinstance(issue, dict)
                       and issue in tool_issues and issue.get('rule_id') in _FAILURE_STATUS
                       and issue.get('severity') in ('blocking', 'review')
                       and issue.get('location', {}).get('calculation_id') == calculation_id
                       and issue.get('location', {}).get('unit_id') == unit_id]
            actual_evidence = [item for item in evidence if isinstance(item, dict)
                               and item.get('calculation_id') == calculation_id
                               and item.get('unit_id') == unit_id]
            if (not sources or len(actual_evidence) != 1
                    or actual_evidence[0].get('status') not in ('FAIL', 'UNKNOWN')
                    or not any(_FAILURE_STATUS[issue['rule_id']] == actual_evidence[0]['status']
                               for issue in sources)):
                return None
            matched.extend(copy.deepcopy(sources))
            old_evidence.append(copy.deepcopy(actual_evidence[0]))
        request = {'section_id': before['section_id'], 'units': copy.deepcopy(units),
                   'calculations': [copy.deepcopy(replacement) for _, replacement in changed],
                   'uncertainties': [], 'calculation_limitations': []}
        checks = check_math(request)
        checked = checks['evidence']
        if len(checked) != len(changed):
            return None
        for _, replacement in changed:
            results = [item for item in checked if item.get('calculation_id') == replacement['id']
                       and item.get('unit_id') == replacement['unit_id']]
            if (len(results) != 1 or results[0].get('status') != 'PASS'
                    or results[0].get('evidence_type') != 'symbolic_check_passed'):
                return None
        return {'schema_version': 1, 'operation': 'independent_calculation_expression_repair',
                'status': 'VERIFIED_CALCULATION_REPAIR_PENDING_FULL_RECHECK',
                'before_hash': digest(before), 'after_hash': digest(after),
                'repair_issues_hash': digest(repair_issues), 'tool_checks_hash': digest(tool_checks),
                'changed_calculation_ids': [original['id'] for original, _ in changed],
                'target_unit_ids': sorted({original['unit_id'] for original, _ in changed}),
                'matched_issues': matched, 'original_evidence': old_evidence, 'checks': checks,
                'body_changed': False, 'requires_full_recheck': True, 'teacher_review': 'NOT_RUN'}
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
