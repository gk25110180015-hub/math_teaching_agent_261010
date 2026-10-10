"""Preserved author doubts, scoped disposition evidence and bounded replay."""
import copy
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from .domain import StrictModel, MathReview
from .util import AgentError, digest, now, scrub, within, write_json


class DoubtEvidence(StrictModel):
    source_key: str
    source_sha256: str
    quote: str = Field(min_length=8, max_length=12000)


class DoubtDisposition(StrictModel):
    uncertainty_id: str
    unit_id: str | None
    disposition: Literal['resolved_by_current_body', 'open_actionable', 'open_dependency']
    reason: str = Field(min_length=12, max_length=6000)
    evidence: list[DoubtEvidence] = Field(max_length=30)
    remaining_dependency: bool
    repair_instruction: str | None = Field(default=None, max_length=6000)


class UncertaintyAssessment(StrictModel):
    items: list[DoubtDisposition] = Field(min_length=1, max_length=100)
    limitations: list[str]


def declared_doubts(section):
    """Only an actual full ID followed by a clear delimiter binds a legacy note."""
    actual = sorted((u['id'] for u in section['units']), key=len, reverse=True)
    if len(actual) != len(set(actual)):
        raise ValueError('Duplicate actual unit IDs')
    result = []
    for index, original in enumerate(section.get('uncertainties', [])):
        if not isinstance(original, str) or not original.strip():
            raise ValueError('A declared doubt must have nonempty original text')
        text = original.lstrip()
        matches = [key for key in actual if text.startswith(key) and len(text) > len(key)
                   and (text[len(key)].isspace() or text[len(key)] in ':：')]
        target = matches[0] if len(matches) == 1 else None
        result.append({'uncertainty_id': 'D' + str(index + 1).zfill(3) + '-' + digest(original)[:16],
                       'source_index': index, 'original_text': original,
                       'original_sha256': digest(original), 'unit_id': target})
    return result


def declared_issues(section):
    return [{'rule_id': 'DECLARED_MATH_UNCERTAINTY', 'severity': 'review',
             'message': item['original_text'], 'location': {'unit_id': item['unit_id']} if item['unit_id'] else {},
             'uncertainty_id': item['uncertainty_id'], 'original_sha256': item['original_sha256'],
             'resolution_status': 'open'} for item in declared_doubts(section)]


def located_math_issues(section, math):
    # The raw check_math output remains unchanged and is kept in the report.
    return [copy.deepcopy(i) for i in math['issues'] if i.get('rule_id') != 'DECLARED_MATH_UNCERTAINTY'] + declared_issues(section)


def prior_same_body_issues(recovery, section):
    """Preserve actual old blockers during the narrow legacy-note migration.

    Only proven duplicate declarations can be represented by the new stable ID.
    The original review and pending state are not modified here.
    """
    state = recovery.state
    if not state.get('pending_issues') or not state.get('last_review_key'):
        return [], []
    try:
        path = within(recovery.p.settings.workspace, state['last_review_key'])
        if not path.is_relative_to(recovery.folder.resolve()):
            raise ValueError('Prior local review outside its controlled folder')
        saved = json.loads(path.read_bytes())
        identity = saved['review_identity']
        if digest(identity) != state['last_review_context_hash'] or saved['retained_issues'] != state['pending_issues']:
            raise ValueError('Prior local review does not match retained state')
        if identity['candidate_hash'] != digest(section) or identity['plan_context_hash'] != recovery.identity['context_hash']:
            return [], []
        raw_math = saved.get('report', {}).get('math', {})
        raw_verified = digest(raw_math) == identity.get('tool_checks_hash')
        raw_declarations = [i for i in raw_math.get('issues', []) if i.get('rule_id') == 'DECLARED_MATH_UNCERTAINTY'] if raw_verified else []
        known = declared_doubts(section)
        kept, mapping = [], []
        for issue in saved['retained_issues']:
            matches = [item for item in known if issue.get('message') == item['original_text']]
            legacy_shape = issue in raw_declarations or (
                set(issue) <= {'severity', 'message'} and issue in saved.get('report', {}).get('issues', [])
                and any(raw.get('message') == issue.get('message') for raw in raw_declarations))
            if legacy_shape and matches:
                mapping.append({'original_issue': copy.deepcopy(issue), 'original_issue_sha256': digest(issue),
                    'uncertainty_ids': [item['uncertainty_id'] for item in matches],
                    'prior_review_key': state['last_review_key'], 'prior_review_sha256': digest(path.read_bytes())})
            else:
                kept.append(copy.deepcopy(issue))
        return kept, mapping
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AgentError('UNCERTAINTY_EVIDENCE_BLOCKED', str(exc)) from None


def uncertainty_contract():
    from .provider import PROMPTS
    from .review_evidence_attribution import attribution_contract
    return {'version': 1, 'helper_sha256': digest(Path(__file__).read_bytes()),
            'prompt_sha256': digest((PROMPTS / 'reviewer_uncertainty.md').read_bytes()),
            'schema_sha256': digest(UncertaintyAssessment.model_json_schema()),
            'ordinary_prompt_sha256': digest((PROMPTS / 'reviewer_math.md').read_bytes()),
            'ordinary_schema_sha256': digest(MathReview.model_json_schema()),
            'attribution_contract': attribution_contract(),
            'provider_sha256': digest(Path(__file__).with_name('provider.py').read_bytes())}


def build_uncertainty_context(plan, section, prior_sections, math, deterministic_issues, mock=False):
    sources = []
    for owner, sections in [('current', [section]), ('prior', prior_sections)]:
        for generated in sections:
            for unit in generated['units']:
                sources.append({'source_key': owner + ':' + unit['id'], 'unit_id': unit['id'],
                    'source_sha256': digest(unit['tex']), 'tex': unit['tex']})
    if len(sources) != len({source['source_key'] for source in sources}):
        raise ValueError('Duplicate supplied uncertainty evidence sources')
    return {'plan': copy.deepcopy(plan), 'section': copy.deepcopy(section),
            'prior_sections': copy.deepcopy(prior_sections), 'tool_checks': copy.deepcopy(math),
            'deterministic_issues': copy.deepcopy(deterministic_issues),
            'declared_doubts': declared_doubts(section), 'sources': sources, 'mock': bool(mock)}


def validate_uncertainty_assessment(response, context):
    result = UncertaintyAssessment.model_validate(response).model_dump()
    expected = {item['uncertainty_id']: item for item in context['declared_doubts']}
    sources = {source['source_key']: source for source in context['sources']}
    ids = [item['uncertainty_id'] for item in result['items']]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError('Every preserved doubt needs exactly one explicit disposition')
    order = {key: n for n, key in enumerate(expected)}
    result['items'].sort(key=lambda item: order[item['uncertainty_id']])
    for item in result['items']:
        original = expected[item['uncertainty_id']]
        if item['unit_id'] != original['unit_id']:
            raise ValueError('Disposition cannot guess or change the declared owner')
        if len(item['reason'].strip()) < 12:
            raise ValueError('A disposition needs a substantive reason')
        for evidence in item['evidence']:
            source = sources.get(evidence['source_key'])
            quote = evidence['quote']
            if not source or evidence['source_sha256'] != source['source_sha256'] or len(''.join(quote.split())) < 8 or quote not in source['tex']:
                raise ValueError('Evidence must be an exact nonempty span in an actual supplied source')
        status = item['disposition']
        if status != 'open_dependency':
            if not item['unit_id'] or not any(e['source_key'] == 'current:' + item['unit_id'] for e in item['evidence']):
                raise ValueError('Resolving or repairing a doubt needs actual target evidence')
        if status == 'resolved_by_current_body' and item['remaining_dependency']:
            raise ValueError('An unverified prerequisite cannot become a resolved proof')
        if status == 'open_actionable':
            if not item['repair_instruction'] or len(item['repair_instruction'].strip()) < 12:
                raise ValueError('An actionable doubt requires a scoped repair instruction')
        elif item['repair_instruction'] is not None:
            raise ValueError('Only an actionable doubt may request content changes')
    return result


def effective_uncertainty_issues(section, assessment):
    items = {item['uncertainty_id']: item for item in assessment['items']}
    result = []
    for issue in declared_issues(section):
        item = items[issue['uncertainty_id']]
        if item['disposition'] == 'resolved_by_current_body':
            continue
        issue['message'] += '\n显式裁定：' + item['reason']
        if item['repair_instruction']:
            issue['message'] += '\n限定修复：' + item['repair_instruction']
        issue['disposition'] = item['disposition']
        issue['disposition_evidence'] = copy.deepcopy(item['evidence'])
        result.append(issue)
    return result


def mock_uncertainty_assessment(context):
    return {'items': [{'uncertainty_id': item['uncertainty_id'], 'unit_id': item['unit_id'],
        'disposition': 'open_dependency', 'reason': '离线演示不核实数学证明或先修依据；原疑点仍未解决，不能据此发布合格讲义。',
        'evidence': [], 'remaining_dependency': True, 'repair_instruction': None}
        for item in context['declared_doubts']], 'limitations': ['MOCK: no mathematical or teacher review performed.']}


class UncertaintyReview:
    """Same mathematical identity keeps one ordinary review and one disposition.

    A job/model preference change alone cannot reopen a completed judgment.
    Transport failure may finish the same frozen slot; all completed invalid
    responses remain blocked. Evidence is never overwritten.
    """
    def __init__(self, pipeline, context):
        self.p = pipeline
        self.context = copy.deepcopy(context)
        self.identity = {'plan_hash': context['plan']['hash'], 'plan_revision': context['plan']['revision'],
                         'context_hash': digest(context), 'contract': uncertainty_contract()}
        self.key = digest(self.identity)
        self.folder = Path(pipeline.root) / 'uncertainty-reviews' / self.key[:24]
        self.path = self.folder / 'state.json'
        self.state = None

    def _write(self, path, value):
        with self.p.store.transaction() as c:
            self.p.store.assert_fence(c, self.p.job)
            write_json(path, value)

    def _save(self):
        self._write(self.path, self.state)

    def _read(self, name):
        if Path(name).name != name or name not in self.state['dependencies']:
            raise ValueError('Unregistered uncertainty evidence')
        raw = (self.folder / name).read_bytes()
        if digest(raw) != self.state['dependencies'][name]:
            raise ValueError('Uncertainty evidence SHA mismatch')
        return json.loads(raw)

    def _evidence(self, name, value):
        path = self.folder / name
        if path.exists():
            if name in self.state['dependencies'] and self._read(name) == value:
                return
            raise ValueError('Uncertainty evidence cannot be overwritten')
        self._write(path, value)
        self.state['dependencies'][name] = digest(path.read_bytes())
        self._save()

    def _load(self):
        if self.state is not None:
            return
        try:
            if self.path.exists():
                self.state = json.loads(self.path.read_bytes())
                if self.state['identity'] != self.identity or self.state['identity_hash'] != self.key:
                    raise ValueError('Uncertainty identity mismatch')
                for name in self.state['dependencies']:
                    self._read(name)
                if self._read('input.json') != self.context:
                    raise ValueError('Uncertainty context mismatch')
            else:
                if self.folder.exists() and any(self.folder.iterdir()):
                    raise ValueError('Uncertainty state missing beside retained evidence')
                self.state = {'schema_version': 1, 'identity': self.identity, 'identity_hash': self.key,
                    'status': 'CREATED', 'calls': 0, 'created_at': now(), 'dependencies': {},
                    'origin_job_id': self.p.job['id'], 'teacher_review': 'NOT_RUN'}
                self._save()
                self._evidence('input.json', self.context)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AgentError('UNCERTAINTY_EVIDENCE_BLOCKED', str(exc)) from None

    def ordinary_review(self, callback, review_context):
        """Freeze completed ordinary issues before any new disposition call."""
        self._load()
        try:
            if 'ordinary-review.json' in self.state['dependencies']:
                review = self._read('ordinary-review.json')
            else:
                if (self.folder / 'ordinary-review.json').exists():
                    raise ValueError('Unregistered completed ordinary review; do not redraw')
                if 'ordinary-context.json' not in self.state['dependencies']:
                    self._evidence('ordinary-context.json', review_context)
                review = callback(self._read('ordinary-context.json'))
                self._evidence('ordinary-review.json', review)
            actual = {u['id'] for u in self.context['section']['units']}
            validated = MathReview.model_validate(review).model_dump()
            if set(validated['checked_unit_ids']) != actual or any(i['unit_id'] not in actual for i in validated['issues']):
                raise ValueError('Saved ordinary review scope mismatch')
            return validated
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AgentError('UNCERTAINTY_EVIDENCE_BLOCKED', str(exc)) from None

    def _emit(self):
        with self.p.store.transaction() as c:
            self.p.store.assert_fence(c, self.p.job)
            self.p.store.event(c, self.p.run['id'], 'math.uncertainty_reviewed', {
                'job_id': self.p.job['id'], 'origin_job_id': self.state['origin_job_id'],
                'plan_hash': self.identity['plan_hash'], 'plan_revision': self.identity['plan_revision'],
                'identity_hash': self.key, 'status': self.state['status'],
                'evidence_key': self.path.relative_to(self.p.settings.workspace).as_posix(),
                'evidence_sha256': digest(self.path.read_bytes()), 'teacher_review': 'NOT_RUN'})

    def evaluate(self):
        self._load()
        try:
            if 'ordinary-review.json' not in self.state['dependencies']:
                raise ValueError('Ordinary review must be preserved before disposition')
            if self.state['status'] == 'INVALID':
                raise AgentError('UNCERTAINTY_REVIEW_BLOCKED', '原数学疑点裁定无效；同一正文不重新抽取通过')
            if self.state['status'] == 'REVIEWED':
                result = validate_uncertainty_assessment(self._read(self.state['response_file']), self.context)
                if result != self._read('assessment.json'):
                    raise ValueError('Saved disposition not justified by its response')
                return self._result(result)
            if self.state['status'] not in ('CREATED', 'STARTED', 'TRANSPORT_PENDING', 'RESPONSE_RECEIVED'):
                raise ValueError('Unknown uncertainty state')
            # A crash may occur after failure evidence was committed but before
            # INVALID/TRANSPORT_PENDING was committed. Never redraw a completed
            # malformed response merely because its state still says STARTED.
            failure_name = 'failure-' + str(self.state['calls']) + '.json'
            if (self.folder / failure_name).exists():
                if failure_name not in self.state['dependencies']:
                    raise ValueError('Orphan failure evidence; do not redraw')
                failure = self._read(failure_name)
                if not failure['retryable_same_slot']:
                    self.state['status'] = 'INVALID'
                    self._save()
                    self._emit()
                    raise AgentError('UNCERTAINTY_REVIEW_BLOCKED', '已保存非传输失败裁定；崩溃恢复保留阻断，不重新抽取通过')
                self.state['status'] = 'TRANSPORT_PENDING'
                self._save()
            if 'assessment-input.json' not in self.state['dependencies']:
                self._evidence('assessment-input.json', {**self.context, 'ordinary_review': self._read('ordinary-review.json')})
            response = self._read(self.state['response_file']) if self.state.get('response_file') in self.state['dependencies'] else None
            if response is None:
                if (self.folder / ('response-' + str(self.state['calls']) + '.json')).exists():
                    raise ValueError('Orphan completed disposition; do not redraw')
                self.state['calls'] += 1
            number = self.state['calls']
            self.state.update(status='STARTED', started_at=now())
            self._save()
            try:
                if response is None:
                    response = self.p.provider.generate('reviewer_uncertainty', self._read('assessment-input.json'), UncertaintyAssessment)
                    self.state['response_file'] = 'response-' + str(number) + '.json'
                    self._evidence(self.state['response_file'], response)
                self.state['status'] = 'RESPONSE_RECEIVED'
                self._save()
                result = validate_uncertainty_assessment(response, self.context)
            except Exception as exc:
                from .model_routing import TRANSIENT_ERROR_CODES
                code = getattr(exc, 'code', None)
                retryable = response is None and not self.state.get('response_file') and code in (
                    set(TRANSIENT_ERROR_CODES) | {'PROVIDER_ALL_UNAVAILABLE', 'PROVIDER_NOT_CONFIGURED', 'BUDGET_EXHAUSTED'})
                self._evidence('failure-' + str(number) + '.json', {'code': code, 'message': scrub(str(exc))[:3000],
                    'at': now(), 'retryable_same_slot': retryable})
                self.state.update(status='TRANSPORT_PENDING' if retryable else 'INVALID')
                self._save()
                self._emit()
                if code == 'BUDGET_EXHAUSTED':
                    raise
                raise AgentError('UNCERTAINTY_REVIEW_BLOCKED', '数学疑点裁定未完成；原正文、普通审阅与失败证据保留') from exc
            self._evidence('assessment.json', result)
            self.state.update(status='REVIEWED', ended_at=now())
            self._save()
            self._emit()
            return self._result(result)
        except AgentError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AgentError('UNCERTAINTY_EVIDENCE_BLOCKED', str(exc)) from None

    def _result(self, assessment):
        return {'identity_hash': self.key, 'assessment': assessment,
                'evidence_key': self.path.relative_to(self.p.settings.workspace).as_posix(),
                'evidence_sha256': digest(self.path.read_bytes()), 'teacher_review': 'NOT_RUN'}, effective_uncertainty_issues(self.context['section'], assessment)
