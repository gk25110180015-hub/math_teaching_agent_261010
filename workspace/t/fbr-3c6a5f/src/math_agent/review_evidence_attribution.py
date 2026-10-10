"""Conservative quote detector and durable adjudication gate; candidate only.

The detector is pure; a hit never discards an issue. The gate preserves evidence
and requests a separate explicit disposition, without editing teaching content.
"""
import hashlib
import json
import re
import copy
from pathlib import Path
from typing import Literal

from pydantic import Field

from math_agent.domain import StrictModel, MathIssue, MathReview
from math_agent.util import AgentError, digest, now, scrub, write_json


class EvidenceSpan(StrictModel):
    unit_id: str
    quote: str = Field(min_length=8, max_length=6000)


class AttributionDecision(StrictModel):
    issue_index: int = Field(ge=0)
    issue_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    disposition: Literal['target_supported', 'dependency_supported', 'misattributed_or_withdrawn', 'unresolved']
    reason: str = Field(min_length=20, max_length=6000)
    target_spans: list[EvidenceSpan] = Field(max_length=6)
    source_spans: list[EvidenceSpan] = Field(max_length=6)
    remaining_issue: MathIssue | None


class AttributionAdjudication(StrictModel):
    decisions: list[AttributionDecision] = Field(min_length=1, max_length=100)
    limitations: list[str]


def attribution_contract():
    from math_agent.provider import PROMPTS
    return {'version': 1, 'helper_sha256': digest(Path(__file__).read_bytes()),
        'reviewer_prompt_sha256': digest((PROMPTS / 'reviewer_math.md').read_bytes()),
        'adjudicator_prompt_sha256': digest((PROMPTS / 'review_evidence_attribution.md').read_bytes()),
        'adjudication_schema_sha256': digest(AttributionAdjudication.model_json_schema())}


def _hash(value):
    raw = value.encode('utf-8') if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _space_only(text):
    return ''.join(text.split())


def _anchors(quote):
    """Retain literal formulas; also consider long untranslated prose spans.

    The second route handles the real response's TeX-free mathematical paraphrase
    without equating that paraphrase to source mathematics. The preserved Chinese
    prose is itself an exact quotation, not a fuzzy or semantic match.
    """
    pieces = re.split(r'…+|\.{3,}', quote)
    pieces += re.findall(r'[\u3400-\u9fff，。；：、！？（）\s]{12,}', quote)
    found = set()
    for piece in pieces:
        normalized = _space_only(piece).strip('，。；：、！？（）')
        letters = sum(char.isalpha() for char in normalized)
        chinese = len(re.findall(r'[\u3400-\u9fff]', normalized))
        if letters < 12 or not (chinese >= 12 or len(normalized) >= 32):
            continue
        if normalized not in found:
            found.add(normalized)
    return sorted(found, key=lambda item: (-len(item), item))


def unit_catalog(units, prior_sections):
    """Use only the bodies actually supplied to this review, not disk history."""
    catalog = {}
    groups = [('prior', section.get('units', [])) for section in prior_sections]
    groups.append(('current', units))
    for owner, group in groups:
        for unit in group:
            identity = unit['id']
            item = {'unit_id': identity, 'owner': owner, 'tex': unit['tex'],
                    'tex_sha256': _hash(unit['tex']), 'relates_to': unit.get('relates_to')}
            if identity in catalog and catalog[identity]['tex'] != item['tex']:
                raise ValueError('Ambiguous supplied unit identity: ' + identity)
            catalog[identity] = item
    return catalog


def detect_attribution_conflicts(review, units, prior_sections=()):
    """Return positive unique ownership conflicts; leave every issue untouched.

    Absence, paraphrases, short formulas, ambiguous matches and correct dependency
    critiques remain outside the detector's conclusion. Even an exact hit still
    needs an explicit mathematical/attribution adjudication before any disposition.
    """
    catalog = unit_catalog(units, prior_sections)
    actual = {unit['id'] for unit in units}
    normalized = {key: _space_only(value['tex']) for key, value in catalog.items()}
    conflicts = []
    for index, issue in enumerate(review['issues']):
        target = issue['unit_id']
        if issue['severity'] not in ('blocking', 'review') or target not in actual:
            continue
        explicit = re.compile(r'(?<![A-Za-z0-9_.])' + re.escape(target)
                              + r'\s*[：:]\s*[「『“"]([^」』”"]{1,6000})[」』”"]', re.S)
        matches = []
        for citation in explicit.finditer(issue['evidence']):
            quote = citation.group(1)
            for anchor in _anchors(quote):
                if anchor in normalized[target]:
                    continue
                owners = [key for key, text in normalized.items() if anchor in text]
                if len(owners) != 1:
                    continue
                source = owners[0]
                matches.append({'quote': quote, 'anchor': anchor,
                    'normalization': 'WHITESPACE_ONLY_NO_MATHEMATICAL_EQUIVALENCE',
                    'source_unit_id': source, 'source_owner': catalog[source]['owner'],
                    'source_tex_sha256': catalog[source]['tex_sha256'],
                    'source_normalized_offset': normalized[source].index(anchor)})
                break
        if matches:
            conflicts.append({'issue_index': index, 'issue_hash': _hash(issue),
                'target_unit_id': target, 'target_tex_sha256': catalog[target]['tex_sha256'],
                'matches': matches, 'status': 'ATTRIBUTION_REQUIRES_VERIFICATION',
                'not_a_mathematical_verdict': True})
    return conflicts


def validate_adjudication(original, conflicts, adjudication, catalog):
    """Check disposition coverage and literal ownership, not mathematical proof."""
    value = AttributionAdjudication.model_validate(adjudication).model_dump()
    expected = {item['issue_index']: item for item in conflicts}
    decisions = value['decisions']
    indices = [decision['issue_index'] for decision in decisions]
    if len(indices) != len(set(indices)) or set(indices) != set(expected):
        raise ValueError('Every original attribution conflict requires one explicit disposition')
    replacements = {}
    for decision in decisions:
        index = decision['issue_index']
        conflict = expected[index]
        target = conflict['target_unit_id']
        sources = {item['source_unit_id'] for item in conflict['matches']}
        if decision['issue_hash'] != conflict['issue_hash']:
            raise ValueError('Disposition does not identify the exact original issue')
        if decision['disposition'] == 'unresolved':
            raise ValueError('Attribution remains explicitly unresolved')
        if not decision['target_spans'] or not decision['source_spans']:
            raise ValueError('Both current target evidence and located source evidence are required')
        for key, allowed in [('target_spans', {target}), ('source_spans', sources)]:
            for span in decision[key]:
                text = _space_only(span['quote'])
                if span['unit_id'] not in allowed or len(text) < 8 or text not in _space_only(catalog[span['unit_id']]['tex']):
                    raise ValueError('Adjudication evidence is absent from its claimed actual unit')
        remaining = decision['remaining_issue']
        if decision['disposition'] == 'misattributed_or_withdrawn':
            if remaining is not None:
                raise ValueError('Withdrawal must explicitly withdraw the original issue')
            # These checked target spans must be explained as counterevidence by the
            # adjudicator. Their mathematical meaning is not a deterministic proof.
            replacements[index] = None
        else:
            if remaining is None or remaining['unit_id'] != target or remaining['severity'] not in ('review', 'blocking'):
                raise ValueError('Supported issue must remain blocking/review on the same in-scope target')
            checked = decision['target_spans'] + decision['source_spans']
            evidence = '\n'.join(span['unit_id'] + ':「' + span['quote'] + '」' for span in checked)
            replacements[index] = {**remaining, 'evidence': evidence + '\n核实依据：' + decision['reason']}
    result = copy.deepcopy(original)
    result['issues'] = [replacements.get(i, issue) for i, issue in enumerate(result['issues'])
                        if i not in replacements or replacements[i] is not None]
    result['limitations'].append('已对明确引文归属冲突进行一次逐项核实并校验引用所在正文；该核实不是形式化证明、教师签字或最终验收。原审阅和裁定证据另存。')
    return MathReview.model_validate(result).model_dump(), value


class EvidenceAttributionGuard:
    """Persist before adjudication; identical retries cannot reroll a blocked review."""
    def __init__(self, pipeline, payload, evidence_dir, label):
        self.p = pipeline
        self.payload = copy.deepcopy(payload)
        self.contract = attribution_contract()
        self.identity = {'payload_hash': digest(payload), 'contract': self.contract,
            'job_id': getattr(pipeline, 'job', {}).get('id'),
            'model_id': getattr(pipeline, 'model_id', 'UNKNOWN'),
            'configured_gpt_model': getattr(getattr(pipeline, 'settings', None), 'model', 'UNKNOWN'),
            'provider': getattr(pipeline, 'run', {}).get('input', {}).get('provider', 'UNKNOWN')}
        self.key = digest(self.identity)
        self.folder = Path(getattr(pipeline, 'root', evidence_dir)) / 'review-attribution' / self.key[:24]
        self.state_path = self.folder / 'state.json'
        self.evidence_dir = Path(evidence_dir)
        self.label = label
        self.state = None

    def _event(self, phase):
        if not all(hasattr(self.p, key) for key in ('store', 'job', 'run')):
            return
        with self.p.store.transaction() as connection:
            self.p.store.assert_fence(connection, self.p.job)
            self.p.store.event(connection, self.p.run['id'], 'review.evidence_attribution',
                {'phase': phase, 'identity_hash': self.key,
                 'evidence_key': self.state_path.relative_to(self.p.settings.workspace).as_posix(),
                 'teacher_review': 'NOT_RUN'})

    def _save(self):
        self._write(self.state_path, self.state)

    def _write(self, path, value):
        if all(hasattr(self.p, key) for key in ('store', 'job')):
            with self.p.store.transaction() as connection:
                self.p.store.assert_fence(connection, self.p.job)
                write_json(path, value)
        else:
            write_json(path, value)

    def _evidence(self, name, value):
        path = self.folder / name
        if path.exists():
            if name in self.state['dependencies'] and self._read(name) == value:
                return
            raise AgentError('REVIEW_EVIDENCE_CACHE_INVALID', '归属核实证据不可覆盖；保留原始记录')
        self._write(path, value)
        self.state['dependencies'][name] = digest(path.read_bytes())
        self._save()

    def _read(self, name):
        if Path(name).name != name or name not in self.state['dependencies']:
            raise ValueError('Invalid attribution evidence path')
        raw = (self.folder / name).read_bytes()
        if digest(raw) != self.state['dependencies'][name]:
            raise ValueError('Attribution evidence hash mismatch')
        return json.loads(raw)

    def _pointer(self):
        self._write(self.evidence_dir / (self.label + '-attribution.json'),
            {'identity_hash': self.key, 'status': self.state['status'],
             'state_path': str(self.state_path), 'state_sha256': digest(self.state_path.read_bytes()),
             'original_review_preserved': True, 'teacher_review': 'NOT_RUN'})

    def replay(self):
        if not self.state_path.exists():
            return None
        try:
            self.state = json.loads(self.state_path.read_bytes())
            if self.state['identity'] != self.identity or self.state['identity_hash'] != self.key:
                raise ValueError('Attribution identity mismatch')
            for name in self.state['dependencies']:
                self._read(name)
            if self._read('review-input.json') != self.payload:
                raise ValueError('Supplied review context changed')
            accepted = self._read('accepted-review-input.json')
            if self.state.get('accepted_payload_hash') != digest(accepted):
                raise ValueError('Actual accepted review context hash changed')
            accepted_base = {key: value for key, value in accepted.items() if key != 'review_validation_feedback'}
            initial_base = {key: value for key, value in self.payload.items() if key != 'review_validation_feedback'}
            if accepted_base != initial_base:
                raise ValueError('Accepted scope retry changed actual supplied mathematical context')
            self._pointer()
            catalog = unit_catalog(self.payload['units'], self.payload.get('prior_sections', []))
            original = self._read('original-review.json')
            conflicts = self._read('conflicts.json')
            if self.state['status'] in ('STARTED', 'TRANSPORT_PENDING', 'RESPONSE_RECEIVED'):
                # Continue the same saved adjudication slot, never the ordinary
                # review. A response already on disk must be consumed, not rerolled.
                return self._adjudicate(original, conflicts, catalog,
                    self._read('adjudication-input.json'), resume=True)
            if self.state['status'] != 'RESOLVED':
                raise AgentError('REVIEW_EVIDENCE_BLOCKED', '相同正文与审阅契约的引文归属尚未可靠核实；原问题和一次核实记录已保留，重试不重新抽取 PASS，也不改正文')
            result, _ = validate_adjudication(original, conflicts,
                                             self._read(self.state['response_file']), catalog)
            if result != self._read('resolved-review.json'):
                raise ValueError('Stored disposition is not justified by its evidence')
            self._event('REPLAYED')
            return result
        except AgentError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AgentError('REVIEW_EVIDENCE_CACHE_INVALID', '引文归属核实证据身份或 SHA 校验失败；不绕过原疑点：' + str(exc)) from None

    def inspect(self, review, accepted_payload=None):
        catalog = unit_catalog(self.payload['units'], self.payload.get('prior_sections', []))
        conflicts = detect_attribution_conflicts(review, self.payload['units'], self.payload.get('prior_sections', []))
        if not conflicts:
            return review
        self.state = {'schema_version': 1, 'identity_hash': self.key, 'identity': self.identity,
            'status': 'CREATED', 'created_at': now(), 'dependencies': {},
            'verification_calls': 0, 'teacher_review': 'NOT_RUN'}
        self._save()
        self._evidence('review-input.json', self.payload)
        accepted_payload = copy.deepcopy(accepted_payload if accepted_payload is not None else self.payload)
        self.state['accepted_payload_hash'] = digest(accepted_payload)
        self._evidence('accepted-review-input.json', accepted_payload)
        self._evidence('original-review.json', review)
        self._evidence('conflicts.json', conflicts)
        verification = {'original_review': review, 'conflicts': conflicts,
            'actual_unit_ids': self.payload['actual_unit_ids'],
            'review_context': accepted_payload, 'provided_unit_catalog': list(catalog.values()),
            'instruction': 'Resolve each original issue explicitly. A positive quote ownership conflict does not prove the mathematical criticism false. Preserve legitimate cross-unit dependency errors. Every disposition needs verbatim actual target and located source spans. A withdrawal needs target counterevidence and a reason that addresses the entire original claim. Do not add issues, reassign issues outside original targets, alter the plan or approve content.'}
        self._evidence('adjudication-input.json', verification)
        return self._adjudicate(review, conflicts, catalog, verification)

    def _adjudicate(self, review, conflicts, catalog, verification, resume=False):
        response_file = self.state.get('response_file')
        saved_response = self._read(response_file) if response_file in self.state['dependencies'] else None
        if saved_response is None:
            # A crash between writing a response and recording its hash must not
            # silently permit another draw. Preserve the orphan for explicit audit.
            previous = self.folder / ('adjudication-response-' + str(self.state['verification_calls']) + '.json')
            if previous.exists() and previous.name not in self.state['dependencies']:
                raise AgentError('REVIEW_EVIDENCE_CACHE_INVALID', '发现未完成登记的核实响应；保留原证据，不重新抽取裁定')
        if saved_response is None:
            self.state['verification_calls'] += 1
        call = self.state['verification_calls']
        self.state.update(status='STARTED', started_at=now())
        self._save()
        self._event('RESUMED' if resume else 'STARTED')
        self._pointer()
        try:
            if saved_response is None:
                response = self.p.provider.generate('review_evidence_attribution', verification, AttributionAdjudication)
                self.state['response_file'] = 'adjudication-response-' + str(call) + '.json'
                self._evidence(self.state['response_file'], response)
            else:
                response = saved_response
            # No later retry may sample a replacement once a completed response is
            # received, including malformed output or a valid unresolved verdict.
            self.state['status'] = 'RESPONSE_RECEIVED'
            self._save()
            result, validated = validate_adjudication(review, conflicts, response, catalog)
            self._evidence('validated-dispositions.json', validated)
            self._evidence('resolved-review.json', result)
        except Exception as exc:
            from math_agent.model_routing import TRANSIENT_ERROR_CODES
            code = getattr(exc, 'code', None)
            retryable = saved_response is None and not self.state.get('response_file') and code in (
                set(TRANSIENT_ERROR_CODES) | {'PROVIDER_ALL_UNAVAILABLE', 'BUDGET_EXHAUSTED', 'PROVIDER_NOT_CONFIGURED'})
            failure = {'type': type(exc).__name__, 'code': code,
                       'message': scrub(str(exc))[:3000], 'at': now(), 'retryable_same_slot': retryable}
            self._evidence('adjudication-failure-' + str(call) + '.json', failure)
            self.state.update(status='TRANSPORT_PENDING' if retryable else 'UNRESOLVED',
                              failure=failure, ended_at=now())
            self._save()
            self._event(self.state['status'])
            self._pointer()
            if code == 'BUDGET_EXHAUSTED':
                raise
            raise AgentError('REVIEW_EVIDENCE_BLOCKED', '引文归属定点核实未形成可靠逐项裁定；首次审阅、输入输出及失败已保留，不继续修改正文') from exc
        self.state.update(status='RESOLVED', ended_at=now())
        self._save()
        self._event('RESOLVED')
        self._pointer()
        return result
