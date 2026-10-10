"""One durable adjudication of a reproduced calculation's provenance dispute.

Original mathematical reviews, declarations, sources and failures are immutable.
Only an explicit, cited provenance-only disposition can withdraw an exact issue.
"""
import copy
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field

from .calculation_review_context import calculation_review_sources
from .domain import StrictModel
from .model_routing import TRANSIENT_ERROR_CODES
from .uncertainty_review import DoubtEvidence, declared_doubts, validate_uncertainty_assessment
from .util import AgentError, canonical, digest, now, scrub, write_json


_ROLE = 'review_calculation_provenance'
_EVENT = 'math.calculation_provenance_reviewed'
_RETRYABLE = set(TRANSIENT_ERROR_CODES) | {'PROVIDER_ALL_UNAVAILABLE', 'BUDGET_EXHAUSTED', 'PROVIDER_NOT_CONFIGURED'}


class ProvenanceDecision(StrictModel):
    issue_id: str
    issue_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    disposition: Literal['retain', 'withdraw_provenance_only']
    reason: str = Field(min_length=20, max_length=6000)
    provenance_only: bool
    remaining_mathematical_concern: bool
    evidence: list[DoubtEvidence] = Field(max_length=30)


class ProvenanceAdjudication(StrictModel):
    decisions: list[ProvenanceDecision] = Field(min_length=1, max_length=100)
    limitations: list[str]


def _contract():
    from .provider import PROMPTS
    return {'version': 1, 'helper_sha256': digest(Path(__file__).read_bytes()),
            'prompt_sha256': digest((PROMPTS / (_ROLE + '.md')).read_bytes()),
            'schema_sha256': digest(ProvenanceAdjudication.model_json_schema())}


def _candidates(issues, packet, section, assessment, sources):
    declarations = {item['uncertainty_id']: item for item in declared_doubts(section)}
    dispositions = {item['uncertainty_id']: item for item in assessment['items']}
    corrections = []
    for correction, source in zip(packet['corrections'], sources):
        origins = correction.get('declaration_origins', [])
        known = [origin['declaration'] for origin in origins
                 if declarations.get(origin['declaration']['uncertainty_id']) == origin['declaration']]
        if known:
            corrections.append((correction, source, known))
    result = []
    for index, issue in enumerate(issues):
        if issue.get('severity', 'blocking') not in ('blocking', 'review'):
            continue
        for correction, source, known in corrections:
            uncertainty_id = issue.get('uncertainty_id')
            if issue.get('rule_id') == 'DECLARED_MATH_UNCERTAINTY':
                matching = [note for note in known if note['uncertainty_id'] == uncertainty_id
                            and issue.get('original_sha256') == note['original_sha256']]
                if (not matching or dispositions.get(uncertainty_id, {}).get('disposition') != 'open_dependency'):
                    continue
            elif (not issue.get('rule_id') and not uncertainty_id
                  and issue.get('unit_id') == correction['unit_id']
                  and re.search(r'(?<![\w.])' + re.escape(correction['calculation_id']) + r'(?![\w.])',
                                str(issue.get('message', '')) + '\n' + str(issue.get('evidence', '')))):
                matching = known
            else:
                continue
            result.append({'issue_id': 'I' + str(index + 1).zfill(3), 'issue_hash': digest(issue),
                'issue': copy.deepcopy(issue), 'calculation_id': correction['calculation_id'],
                'unit_id': correction['unit_id'], 'uncertainty_id': uncertainty_id,
                'source_key': source['source_key'],
                'origin_declarations': copy.deepcopy(matching),
                'origin_chains': [{'patch_sha256': origin['patch']['sha256'],
                    'ordinary_context_sha256': origin['ordinary_context_source']['sha256'],
                    'ordinary_review_sha256': origin['ordinary_review_source']['sha256']}
                    for origin in correction['declaration_origins'] if origin['declaration'] in matching],
                'previous_request': copy.deepcopy(correction['previous_request'])})
            break
    if len(result) > 100:
        raise ValueError('Calculation provenance adjudication exceeds its issue budget')
    return result


def _validate(response, payload, context):
    result = ProvenanceAdjudication.model_validate(response).model_dump()
    candidates = {item['issue_id']: item for item in payload['candidates']}
    decisions = result['decisions']
    ids = [item['issue_id'] for item in decisions]
    if len(ids) != len(set(ids)) or set(ids) != set(candidates):
        raise ValueError('Every frozen provenance candidate needs exactly one disposition')
    sources = {source['source_key']: source for source in payload['sources']}
    for decision in decisions:
        candidate = candidates[decision['issue_id']]
        if decision['issue_hash'] != candidate['issue_hash']:
            raise ValueError('Provenance disposition changed the original issue identity')
        for evidence in decision['evidence']:
            source = sources.get(evidence['source_key'])
            if (not source or source['source_sha256'] != evidence['source_sha256']
                    or len(''.join(evidence['quote'].split())) < 8
                    or evidence['quote'] not in source['tex']):
                raise ValueError('Provenance evidence must be an exact registered source span')
        if decision['disposition'] == 'retain':
            continue
        if not decision['provenance_only'] or decision['remaining_mathematical_concern']:
            raise ValueError('A remaining mathematical concern cannot be withdrawn as provenance')
        if not any(e['source_key'] == 'current:' + candidate['unit_id'] for e in decision['evidence']):
            raise ValueError('Provenance withdrawal requires actual current-body evidence')
        historical = '\n'.join(e['quote'] for e in decision['evidence']
                               if e['source_key'] == candidate['source_key'])
        if (canonical(candidate['previous_request']) not in historical
                or not any(canonical(note) in historical for note in candidate['origin_declarations'])
                or not any(all(value in historical for value in chain.values())
                           for chain in candidate['origin_chains'])):
            raise ValueError('Provenance withdrawal must cite the old request and exact declaration origin')
    # The ordinary uncertainty validator still owns every final declaration's
    # metadata, current-body requirement, disposition and dependency rules.
    _apply(result, payload, payload['issues'], context)
    return result


def _apply(response, payload, issues, context):
    decisions = {item['issue_id']: item for item in response['decisions']}
    by_hash = {}
    by_declaration = {}
    for candidate in payload['candidates']:
        decision = decisions[candidate['issue_id']]
        by_hash.setdefault(candidate['issue_hash'], []).append(decision)
        if candidate['uncertainty_id']:
            by_declaration.setdefault(candidate['uncertainty_id'], []).append(decision)
    withdrawn = {key for key, values in by_hash.items()
                 if all(item['disposition'] == 'withdraw_provenance_only' for item in values)}
    effective = [copy.deepcopy(issue) for issue in issues if digest(issue) not in withdrawn]
    assessment = copy.deepcopy(payload['assessment'])
    for item in assessment['items']:
        values = by_declaration.get(item['uncertainty_id'], [])
        if (not values or not all(value['disposition'] == 'withdraw_provenance_only' for value in values)
                or any(issue.get('uncertainty_id') == item['uncertainty_id'] for issue in effective)):
            continue
        decision = values[0]
        item.update(disposition='resolved_by_current_body', reason=decision['reason'],
                    evidence=copy.deepcopy(decision['evidence']), remaining_dependency=False, repair_instruction=None)
    checked = validate_uncertainty_assessment(assessment, context)
    return effective, checked


class _Archive:
    def __init__(self, p, guard):
        self.p = p
        self.folder = Path(p.root) / 'calculation-provenance-reviews' / guard.key[:24]
        self.path = self.folder / 'state.json'
        if (not self.folder.resolve().is_relative_to(Path(p.root).resolve())
                or not self.path.resolve().is_relative_to(self.folder.resolve())):
            raise ValueError('Provenance archive escaped its controlled run')
        self.state = None

    def read(self, name):
        path = self.folder / name
        if (Path(name).name != name or not path.resolve().is_relative_to(self.folder.resolve())
                or name not in self.state['dependencies']):
            raise ValueError('Unregistered provenance adjudication evidence')
        raw = path.read_bytes()
        if digest(raw) != self.state['dependencies'][name]:
            raise ValueError('Provenance adjudication evidence SHA mismatch')
        return json.loads(raw)

    def save(self):
        with self.p.store.transaction() as connection:
            self.p.store.assert_fence(connection, self.p.job)
            write_json(self.path, self.state)

    def evidence(self, name, value):
        path = self.folder / name
        if path.exists():
            if name in self.state['dependencies'] and self.read(name) == value:
                return
            raise ValueError('Provenance adjudication evidence cannot be overwritten')
        with self.p.store.transaction() as connection:
            self.p.store.assert_fence(connection, self.p.job)
            write_json(path, value)
            self.state['dependencies'][name] = digest(path.read_bytes())
            write_json(self.path, self.state)

    def receipt(self):
        payload = {'identity_hash': self.state['identity_hash'],
            'source_identity_hash': self.state['source_identity_hash'],
            'evidence_key': (self.folder / 'result.json').relative_to(self.p.settings.workspace).as_posix(),
            'evidence_sha256': self.state['dependencies']['result.json'], 'teacher_review': 'NOT_RUN'}
        with self.p.store.transaction() as connection:
            self.p.store.assert_fence(connection, self.p.job)
            rows = connection.execute('SELECT payload_json FROM events WHERE run_id=? AND type=?',
                                      (self.p.run['id'], _EVENT)).fetchall()
            previous = [json.loads(row['payload_json']) for row in rows
                        if json.loads(row['payload_json']).get('source_identity_hash') == payload['source_identity_hash']]
            if previous and previous != [payload]:
                raise ValueError('Conflicting provenance adjudication receipt')
            if not previous:
                self.p.store.event(connection, self.p.run['id'], _EVENT, payload)
        return {**payload, 'status': 'ADJUDICATED', 'semantic_verdicts': 1,
                'original_reviews_preserved': True}


def apply_calculation_provenance_review(p, guard, section, math, packet, issues, assessment):
    """Return effective issues, effective assessment and an immutable audit.

    One source guard has at most one adjudication slot. On replay, decisions are
    applied only to exact frozen issue hashes; newly supplied issues are retained.
    """
    if not packet or not any(item.get('declaration_origins') for item in packet.get('corrections', [])):
        return copy.deepcopy(issues), copy.deepcopy(assessment), None
    try:
        if (not guard.folder.resolve().is_relative_to(Path(p.root).resolve())
                or not guard.path.resolve().is_relative_to(guard.folder.resolve())):
            raise ValueError('Provenance source guard escaped its controlled run')
        if not guard.path.exists():
            raise ValueError('Provenance adjudication needs an existing reviewed source guard')
        guard._load()
        source_raw = guard.path.read_bytes()
        if (json.loads(source_raw) != guard.state or guard.state['status'] != 'REVIEWED'
                or guard.state['identity_hash'] != guard.key or digest(guard.identity) != guard.key):
            raise ValueError('Provenance adjudication source guard is not a frozen valid review')
        for name in guard.state['dependencies']:
            guard._read(name)
        context = guard._read('input.json')
        if (context != guard.context or context['section'] != section or context['tool_checks'] != math
                or context.get('calculation_recovery_evidence') != packet
                or guard._read('assessment.json') != assessment
                or context['declared_doubts'] != declared_doubts(section)):
            raise ValueError('Provenance adjudication differs from its frozen mathematical context')
        validate_uncertainty_assessment(assessment, context)
        sources = calculation_review_sources(packet)
        if any(source not in context['sources'] for source in sources):
            raise ValueError('Provenance source is not registered in the original review')
        payload_base = {'source_guard': {'identity_hash': guard.key,
                'state_sha256': digest(source_raw), 'dependencies': copy.deepcopy(guard.state['dependencies'])},
            'section': copy.deepcopy(section), 'math': copy.deepcopy(math), 'packet': copy.deepcopy(packet),
            'assessment': copy.deepcopy(assessment), 'ordinary_review': guard._read('ordinary-review.json'),
            'sources': copy.deepcopy(context['sources'])}
        fixed = {'contract': _contract(), 'source_identity_hash': guard.key, 'payload_base_hash': digest(payload_base),
            'model_id': getattr(p, 'model_id', 'UNKNOWN'),
            'model': getattr(getattr(p, 'settings', None), 'model', 'UNKNOWN'),
            'provider': p.run.get('input', {}).get('provider', 'UNKNOWN')}
        archive = _Archive(p, guard)
        if archive.path.exists():
            archive.state = json.loads(archive.path.read_bytes())
            if archive.state['fixed_identity'] != fixed:
                raise ValueError('Frozen provenance adjudication identity changed; cannot redraw')
            for name in archive.state['dependencies']:
                archive.read(name)
            payload = archive.read('input.json')
            identity = {**fixed, 'input_hash': digest(payload)}
            if (archive.state['identity'] != identity or archive.state['identity_hash'] != digest(identity)
                    or {key: value for key, value in payload.items() if key not in ('issues', 'candidates')} != payload_base
                    or payload['candidates'] != _candidates(payload['issues'], packet, section, assessment, sources)):
                raise ValueError('Frozen provenance adjudication input or candidates changed')
            if archive.state['status'] == 'TRANSPORT_PENDING':
                failure = archive.read(archive.state['failure_file'])
                if (failure.get('retryable_same_slot') is not True or failure.get('code') not in _RETRYABLE
                        or 'response.json' in archive.state['dependencies'] or (archive.folder / 'response.json').exists()):
                    raise ValueError('Provenance transport retry has a response or lacks its explicit transport failure')
            elif archive.state['status'] != 'COMPLETE':
                raise AgentError('CALCULATION_PROVENANCE_REVIEW_BLOCKED',
                                 '来源争议的一次裁定未完成或无效；原始证据保留，不重新抽取裁定')
            else:
                response = _validate(archive.read('response.json'), payload, context)
                expected_issues, expected_assessment = _apply(response, payload, payload['issues'], context)
                saved = archive.read('result.json')
                if (saved['effective_issues'] != expected_issues or saved['effective_assessment'] != expected_assessment
                        or saved['adjudication'] != response or saved['identity_hash'] != archive.state['identity_hash']):
                    raise ValueError('Cached provenance adjudication result changed')
        else:
            if archive.folder.exists() and any(archive.folder.iterdir()):
                raise ValueError('Provenance state missing beside retained evidence; cannot redraw')
            candidates = _candidates(issues, packet, section, assessment, sources)
            if not candidates:
                return copy.deepcopy(issues), copy.deepcopy(assessment), None
            payload = {**payload_base, 'issues': copy.deepcopy(issues), 'candidates': candidates}
            identity = {**fixed, 'input_hash': digest(payload)}
            archive.state = {'schema_version': 1, 'fixed_identity': fixed, 'identity': identity,
                'identity_hash': digest(identity), 'source_identity_hash': guard.key,
                'status': 'CREATED', 'dependencies': {}, 'calls': 0, 'teacher_review': 'NOT_RUN', 'created_at': now()}
            archive.save()
            archive.evidence('input.json', payload)
        if archive.state['status'] != 'COMPLETE':
            number = archive.state['calls'] + 1
            archive.state.update(status='STARTED', calls=number)
            archive.save()
            raw_response = None
            try:
                provider = p.provider
                # Disable schema resampling for this separately frozen verdict.
                # Transport routing keeps its existing policy and request budget.
                if hasattr(provider, 'settings') and hasattr(provider.settings, 'model_copy'):
                    provider = copy.copy(provider)
                    provider.settings = provider.settings.model_copy(update={'max_schema_repair_attempts': 0})
                raw_response = provider.generate(_ROLE, payload, ProvenanceAdjudication)
                archive.evidence('response.json', raw_response)
                response = _validate(raw_response, payload, context)
                effective, effective_assessment = _apply(response, payload, payload['issues'], context)
            except Exception as exc:
                code = getattr(exc, 'code', type(exc).__name__)
                retryable = (raw_response is None and not (archive.folder / 'response.json').exists()
                             and code in _RETRYABLE)
                failure_name = 'failure-' + str(number) + '.json'
                archive.evidence(failure_name, {'code': code, 'message': scrub(str(exc))[:3000],
                                                'retryable_same_slot': retryable})
                archive.state.update(status='TRANSPORT_PENDING' if retryable else 'INVALID', failure_file=failure_name)
                archive.save()
                if code == 'BUDGET_EXHAUSTED':
                    raise
                raise AgentError('CALCULATION_PROVENANCE_REVIEW_BLOCKED',
                    '来源裁定尚未收到完整响应；可恢复同一固定请求' if retryable else
                    '来源争议的一次裁定无效；原始响应和问题保留，不重新抽取裁定') from None
            archive.evidence('result.json', {'schema_version': 1, 'identity_hash': archive.state['identity_hash'],
                'effective_issues': effective, 'effective_assessment': effective_assessment,
                'adjudication': response, 'original_issues': copy.deepcopy(payload['issues']),
                'original_assessment': copy.deepcopy(payload['assessment']), 'teacher_review': 'NOT_RUN'})
            archive.state['status'] = 'COMPLETE'
            archive.save()
        effective, effective_assessment = _apply(response, payload, issues, context)
        return effective, effective_assessment, archive.receipt()
    except AgentError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise AgentError('UNCERTAINTY_EVIDENCE_BLOCKED', str(exc)) from None
