"""Reproduce frozen failed calculations so reviews can compare actual requests.

This supplies historical evidence, not a verdict or permission to clear doubts.
No candidate, archived input, review state or database row is modified.
"""
import copy
import json
from pathlib import Path

from .mathcheck import check_math
from .util import AgentError, canonical, digest, within


_EXPRESSION_FIELDS = {'equivalence': 'lhs', 'derivative': 'expression',
                      'limit': 'expression', 'series': 'term'}
_MAX_ARCHIVES = 512
_MAX_INPUT_BYTES = 16 * 1024 * 1024
_MAX_CORRECTIONS = 100


def _read_json(path, maximum=_MAX_INPUT_BYTES):
    if path.stat().st_size > maximum:
        raise ValueError('Calculation provenance archive exceeds its read budget')
    raw = path.read_bytes()
    return json.loads(raw), raw


def _requests(section):
    calculations = section.get('calculations', [])
    if not isinstance(calculations, list) or len(calculations) > 100:
        raise ValueError('Calculation provenance requires bounded request lists')
    result = {}
    units = {unit['id'] for unit in section['units']}
    for calculation in calculations:
        if not isinstance(calculation, dict):
            raise ValueError('Calculation provenance request is not an object')
        key = calculation.get('id')
        # Legacy unbound requests cannot establish a correction's ownership.
        if not isinstance(key, str) or not key or calculation.get('unit_id') not in units:
            continue
        if key in result:
            raise ValueError('Calculation provenance request IDs are ambiguous')
        result[key] = calculation
    return result


def _one_evidence(math, request, status, evidence_type):
    evidence = math.get('evidence', [])
    if not isinstance(evidence, list):
        raise ValueError('Calculation provenance evidence list is invalid')
    matched = [item for item in evidence if isinstance(item, dict)
               and item.get('calculation_id') == request['id']
               and item.get('unit_id') == request['unit_id']]
    if len(matched) > 1:
        raise ValueError('Calculation provenance has ambiguous results for one request')
    if (not matched or matched[0].get('status') != status
            or matched[0].get('evidence_type') != evidence_type):
        return None
    return matched[0]


def _declaration_origins(recovery, section, corrections, archives):
    """Link preserved notes to pinned proposals and their frozen review inputs."""
    from .local_patch import LocalPatch, apply_local_patch
    from .uncertainty_review import declared_doubts

    declarations = declared_doubts(section)
    dependencies = recovery.state.get('evidence_dependencies', [])
    if not declarations or not dependencies:
        return
    if not isinstance(dependencies, list) or len(dependencies) > _MAX_ARCHIVES:
        raise ValueError('Calculation declaration dependency count exceeds its bounds')
    workspace = Path(recovery.p.settings.workspace)
    build_root = Path(getattr(recovery.p, 'build_root', workspace / 'b' / recovery.p.run['id'][:16])).resolve()
    # Origin recovery concerns notes created before calculation provenance was
    # supplied. New reviews of this packet cannot become its own source.
    records = [record for record in archives if 'calculation_recovery_evidence' not in record['input']]
    by_section = {}
    for record in records:
        by_section.setdefault(digest(record['input']['section']), record)

    def input_source(record):
        return {'input_key': record['path'].relative_to(workspace).as_posix(),
                'input_sha256': record['raw_sha256'], 'identity_hash': record['state']['identity_hash'],
                'context_hash': record['state']['identity']['context_hash']}

    def registered(record, name):
        path = record['path'].parent / name
        if not path.resolve().is_relative_to(record['path'].parent.resolve()):
            raise ValueError('Calculation declaration evidence escaped its registered folder')
        value, raw = _read_json(path)
        if digest(raw) != record['state']['dependencies'].get(name):
            raise ValueError('Calculation declaration review evidence SHA mismatch')
        return value, {'key': path.relative_to(workspace).as_posix(), 'sha256': digest(raw)}

    emitted = {id(item): {} for item in corrections}
    for dependency in sorted(dependencies, key=lambda item: item['key']):
        path = within(workspace, dependency['key'])
        if not path.is_relative_to(Path(recovery.p.root).resolve()) and not path.is_relative_to(build_root):
            raise ValueError('Calculation declaration proposal escaped its controlled run')
        if not (path.name.endswith('-patch.json') or path.name == 'proposal.json'):
            continue
        patch, raw = _read_json(path)
        if digest(raw) != dependency['hash']:
            raise ValueError('Calculation declaration pinned proposal SHA mismatch')
        if not isinstance(patch, dict):
            continue
        notes = patch.get('uncertainties_append', [])
        relevant = [note for note in declarations if note['original_text'] in notes]
        if not relevant or patch.get('section_id') != section['section_id']:
            continue
        LocalPatch.model_validate(patch)
        targets = [item['unit_id'] for item in patch['replacements']]
        for before in records:
            prior = before['input']['section']
            added = [note for note in relevant if note['original_text'] not in prior.get('uncertainties', [])]
            applicable = [item for item in corrections if item['unit_id'] in targets
                          and _requests(prior).get(item['calculation_id']) == item['current_request']]
            if not added or not applicable:
                continue
            try:
                result, _ = apply_local_patch(prior, targets, patch)
            except ValueError:
                # A different historical section is not this proposal's parent.
                continue
            after = by_section.get(digest(result))
            if after is None or after['input']['section'] != result:
                continue
            ordinary_context, context_source = registered(before, 'ordinary-context.json')
            ordinary_review, review_source = registered(before, 'ordinary-review.json')
            identity = ordinary_context['local_recovery']['current_review_identity']
            if (identity['candidate_hash'] != digest(prior)
                    or identity['tool_checks_hash'] != digest(before['input']['tool_checks'])
                    or ordinary_context['tool_checks'] != before['input']['tool_checks']
                    or ordinary_context['plan']['hash'] != before['input']['plan']['hash']
                    or ordinary_context['plan']['revision'] != before['input']['plan']['revision']
                    or ordinary_context['scope']['current_section']['id'] != section['section_id']):
                raise ValueError('Calculation declaration parent review does not match its frozen section')
            unresolved = ordinary_context['local_recovery']['unresolved_issues']
            issues = ordinary_review['issues']
            if not isinstance(unresolved, list) or not isinstance(issues, list):
                raise ValueError('Calculation declaration parent issue lists are invalid')
            for correction in applicable:
                for note in added:
                    origin = {'declaration': copy.deepcopy(note),
                        'patch': {'key': dependency['key'], 'sha256': digest(raw), 'content': copy.deepcopy(patch)},
                        'before_section_hash': digest(prior), 'after_section_hash': digest(result),
                        'before_source': input_source(before), 'after_source': input_source(after),
                        'ordinary_context_source': context_source, 'ordinary_review_source': review_source,
                        'prior_unresolved_issues': copy.deepcopy(unresolved), 'ordinary_issues': copy.deepcopy(issues)}
                    # Multiple identical frozen inputs must not duplicate one origin.
                    key = digest([note['original_sha256'], digest(raw), digest(prior), digest(result), unresolved, issues])
                    emitted[id(correction)].setdefault(key, origin)
                    if sum(len(items) for items in emitted.values()) > _MAX_CORRECTIONS:
                        raise ValueError('Calculation declaration origins exceed their bounded budget')
    for correction in corrections:
        origins = emitted[id(correction)]
        if origins:
            correction['declaration_origins'] = [origins[key] for key in sorted(origins)]


def build_calculation_review_context(recovery, section, current_math):
    """Return stable, independently reproduced before/after evidence or None."""
    try:
        plan = recovery.p.run['plan']
        if plan['hash'] != recovery.identity['plan_hash']:
            raise ValueError('Calculation provenance differs from the approved recovery plan')
        if section['section_id'] != recovery.spec['id']:
            raise ValueError('Calculation provenance section identity differs from recovery')
        current = _requests(section)
        passed = {key: evidence for key, request in current.items()
                  if (evidence := _one_evidence(current_math, request, 'PASS', 'symbolic_check_passed')) is not None
                  and request.get('kind') in _EXPRESSION_FIELDS}
        if not passed:
            return None
        base = Path(recovery.p.root) / 'uncertainty-reviews'
        if not base.exists():
            return None
        if not base.resolve().is_relative_to(Path(recovery.p.root).resolve()):
            raise ValueError('Calculation provenance root escaped the controlled run')
        folders = sorted((path for path in base.iterdir() if path.is_dir()), key=lambda path: path.name)
        if len(folders) > _MAX_ARCHIVES:
            raise ValueError('Calculation provenance archive count exceeds its scan budget')
        selected = {}
        archives = []
        for folder in folders:
            if not folder.resolve().is_relative_to(base.resolve()):
                raise ValueError('Calculation provenance archive escaped the controlled root')
            state_path, input_path = folder / 'state.json', folder / 'input.json'
            if any(not path.resolve().is_relative_to(folder.resolve()) for path in (state_path, input_path)):
                raise ValueError('Calculation provenance file escaped its registered folder')
            if not state_path.exists():
                if input_path.exists():
                    orphan, _ = _read_json(input_path)
                    if (orphan.get('section', {}).get('section_id') == section['section_id']
                            and orphan.get('plan', {}).get('hash') == plan['hash']):
                        raise ValueError('Relevant frozen calculation input has no registered state')
                continue
            state, _ = _read_json(state_path)
            identity = state['identity']
            if (digest(identity) != state['identity_hash'] or folder.name != state['identity_hash'][:24]):
                raise ValueError('Calculation provenance uncertainty identity SHA mismatch')
            if identity.get('plan_hash') != plan['hash'] or identity.get('plan_revision') != plan['revision']:
                continue
            previous_input, raw = _read_json(input_path)
            if (digest(raw) != state['dependencies']['input.json']
                    or digest(previous_input) != identity['context_hash']
                    or previous_input['plan']['hash'] != plan['hash']
                    or previous_input['plan']['revision'] != plan['revision']):
                raise ValueError('Calculation provenance registered input or plan SHA mismatch')
            previous_section = previous_input['section']
            if previous_section['section_id'] != section['section_id']:
                continue
            archives.append({'input': previous_input, 'state': state, 'path': input_path,
                             'raw_sha256': digest(raw)})
            for key, previous in _requests(previous_section).items():
                if key not in passed:
                    continue
                request = current[key]
                field = _EXPRESSION_FIELDS[request['kind']]
                if (field not in previous or field not in request or previous[field] == request[field]
                        or {name: value for name, value in previous.items() if name != field}
                        != {name: value for name, value in request.items() if name != field}):
                    continue
                evidence = _one_evidence(previous_input['tool_checks'], previous,
                                         'FAIL', 'symbolic_check_failed')
                if evidence is None:
                    continue
                if 'result' not in evidence:
                    raise ValueError('Frozen symbolic failure lacks its reproducible result')
                dedup = digest([key, previous, evidence['result']])
                if dedup not in selected:
                    selected[dedup] = {
                        'calculation_id': key, 'unit_id': request['unit_id'], 'expression_field': field,
                        'previous_request': copy.deepcopy(previous), 'current_request': copy.deepcopy(request),
                        'previous_evidence': copy.deepcopy(evidence), 'current_evidence': copy.deepcopy(passed[key]),
                        'source': {'input_key': input_path.relative_to(recovery.p.settings.workspace).as_posix(),
                                   'input_sha256': digest(raw), 'identity_hash': state['identity_hash'],
                                   'context_hash': identity['context_hash']}}
                if len(selected) > _MAX_CORRECTIONS:
                    raise ValueError('Calculation provenance corrections exceed the bounded checker budget')
        if not selected:
            return None
        corrections = [selected[key] for key in sorted(selected)]
        replay = check_math({'section_id': section['section_id'], 'units': copy.deepcopy(section['units']),
                             'calculations': [copy.deepcopy(item['previous_request']) for item in corrections],
                             'uncertainties': [], 'calculation_limitations': []})
        reproduced = replay['evidence']
        if len(reproduced) != len(corrections):
            raise ValueError('Historical calculation replay did not cover every selected request')
        for item, result in zip(corrections, reproduced):
            if (result.get('calculation_id') != item['calculation_id']
                    or result.get('unit_id') != item['unit_id'] or result.get('status') != 'FAIL'
                    or result.get('evidence_type') != 'symbolic_check_failed'
                    or result.get('result') != item['previous_evidence']['result']):
                raise ValueError('Frozen failed calculation cannot be reproduced by the bounded checker')
            item['reproduced_previous_evidence'] = copy.deepcopy(result)
        _declaration_origins(recovery, section, corrections, archives)
        return {'schema_version': 1, 'status': 'HISTORICAL_FAILURE_REPRODUCED_CURRENT_CHECK_PASSED',
                'section_id': section['section_id'], 'corrections': corrections,
                'instruction': 'These are different frozen calculation requests for the same calculation ID. '
                    'Compare the exact previous and current ASTs and their results. The previous failure remains '
                    'historical evidence; it is not a second result for the current request. Reconsider retained '
                    'issues using these actual inputs without deleting them automatically. This packet neither '
                    'proves the whole section correct nor grants teacher approval.',
                'teacher_review': 'NOT_RUN'}
    except AgentError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise AgentError('UNCERTAINTY_EVIDENCE_BLOCKED', str(exc)) from None


def calculation_review_sources(packet):
    """Expose an already verified comparison as citable, non-body sources.

    The caller must use the packet returned by build_calculation_review_context.
    This projection makes its actual inputs admissible under the existing source
    citation protocol; it does not change any disposition or current-body rule.
    """
    if packet is None:
        return []
    try:
        if (packet['schema_version'] != 1
                or packet['status'] != 'HISTORICAL_FAILURE_REPRODUCED_CURRENT_CHECK_PASSED'
                or packet['teacher_review'] != 'NOT_RUN'):
            raise ValueError('Calculation source requires a verified comparison packet')
        corrections = packet['corrections']
        if not isinstance(corrections, list) or not 1 <= len(corrections) <= _MAX_CORRECTIONS:
            raise ValueError('Calculation source comparison count exceeds its bounds')
        sources = []
        seen = set()
        for item in corrections:
            previous, current = item['previous_request'], item['current_request']
            field = _EXPRESSION_FIELDS[current['kind']]
            if (item['expression_field'] != field
                    or previous['id'] != current['id'] or current['id'] != item['calculation_id']
                    or previous['unit_id'] != current['unit_id'] or current['unit_id'] != item['unit_id']
                    or previous[field] == current[field]
                    or {key: value for key, value in previous.items() if key != field}
                    != {key: value for key, value in current.items() if key != field}):
                raise ValueError('Calculation source requests do not describe the verified correction')
            old, replay, present = (item['previous_evidence'], item['reproduced_previous_evidence'],
                                    item['current_evidence'])
            for evidence, status, kind in (
                    (old, 'FAIL', 'symbolic_check_failed'),
                    (replay, 'FAIL', 'symbolic_check_failed'),
                    (present, 'PASS', 'symbolic_check_passed')):
                if (evidence['status'] != status or evidence['evidence_type'] != kind
                        or evidence['calculation_id'] != item['calculation_id']
                        or evidence['unit_id'] != item['unit_id'] or 'result' not in evidence):
                    raise ValueError('Calculation source lacks its bound symbolic evidence')
            if replay['result'] != old['result']:
                raise ValueError('Calculation source historical result was not reproduced')
            source = item['source']
            if (not isinstance(source['input_key'], str) or not source['input_key']
                    or any(not isinstance(source[key], str) or len(source[key]) != 64
                           or any(char not in '0123456789abcdef' for char in source[key])
                           for key in ('input_sha256', 'identity_hash', 'context_hash'))):
                raise ValueError('Calculation source lacks its frozen input identity')
            text = '\n'.join([
                '核算修正的可复核归档证据；这不是讲义正文，也不是教师验收。',
                '核算编号：' + item['calculation_id'] + '；所属实际单元：' + item['unit_id'] + '。',
                '下面给出产生历史结果的完整旧请求，以及当前请求；两者仅 ' + field + ' 表达式不同，其余字段相同。',
                '历史完整请求（JSON AST）：' + canonical(previous),
                '历史归档核算：FAIL；结果 ' + canonical(old['result']) + '。完整证据：' + canonical(old),
                '对该旧请求独立重放：FAIL；结果 ' + canonical(replay['result']) + '。完整证据：' + canonical(replay),
                '当前完整请求（JSON AST）：' + canonical(current),
                '当前核算：PASS；结果 ' + canonical(present['result']) + '。完整证据：' + canonical(present),
                '旧请求的冻结输入来源（归档路径、原始文件 SHA256、身份及上下文 SHA256）：' + canonical(source),
                '历史 FAIL 记录完整保留，针对的是上述旧请求，并非当前请求的第二个核算结果。',
                '本记录只证明这两项具体核算的输入、结果及历史来源；不自动消除任何疑点，也不证明整份正文正确。'
            ])
            if item.get('declaration_origins'):
                text += ('\n保留声明的内部生成来源：以下原始补丁逐字追加了该声明；将已固定 SHA 的补丁应用于已注册的前稿，'
                         '精确得到已注册的后稿。所列问题是该前稿审阅实际收到的历史未决问题与实际返回的问题。'
                         '这提供声明生成时的已知输入及追加来源，不预设声明已解决，也不猜测未提供的外部记录。\n'
                         + canonical(item['declaration_origins']))
            key = 'calculation:' + digest(item)
            if key in seen:
                raise ValueError('Duplicate supplied calculation evidence sources')
            seen.add(key)
            sources.append({'source_key': key, 'unit_id': item['unit_id'],
                            'source_sha256': digest(text), 'tex': text})
        return sources
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise AgentError('UNCERTAINTY_EVIDENCE_BLOCKED', str(exc)) from None
