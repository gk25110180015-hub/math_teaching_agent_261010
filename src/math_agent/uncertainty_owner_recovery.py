"""Replay one redundant owner-field error without changing a mathematical verdict.

The preserved declaration owns its metadata.  An unlocated resolved doubt may
cite a current unit without becoming bound to that unit or authorizing a patch.
Original responses and INVALID states are never modified or sampled again.
"""
import copy
import json
from pathlib import Path

from .domain import MathReview
from .util import AgentError, digest, uid


_OWNER_ERROR = 'Disposition cannot guess or change the declared owner'
_EVENT = 'math.uncertainty_owner_recovered'


def _record_bytes(record):
    return json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8')


def write_json(path, record):
    """Write exact UTF-8/LF bytes atomically, including on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + uid()[:12] + '.tmp')
    temporary.write_bytes(_record_bytes(record))
    temporary.replace(path)


def _persist(guard, path, record, receipt):
    """One immutable record plus an idempotent receipt; tolerate a commit crash."""
    expected = _record_bytes(record)
    with guard.p.store.transaction() as connection:
        guard.p.store.assert_fence(connection, guard.p.job)
        rows = connection.execute(
            'SELECT payload_json FROM events WHERE run_id=? AND type=?',
            (guard.p.run['id'], _EVENT)).fetchall()
        receipts = [json.loads(row['payload_json']) for row in rows
                    if json.loads(row['payload_json']).get('source_identity_hash') == guard.key]
        if receipts and receipts != [receipt]:
            raise ValueError('Conflicting uncertainty owner-recovery receipt')
        if path.exists():
            if path.read_bytes() != expected:
                raise ValueError('Immutable uncertainty owner-recovery evidence changed')
        elif receipts:
            raise ValueError('Completed uncertainty owner-recovery evidence is missing')
        else:
            # write_json uses an atomic sibling replacement.  If the database
            # transaction is interrupted afterwards, exactly these bytes may
            # be adopted on retry; neither old evidence nor a verdict changes.
            write_json(path, record)
        source = guard.path.read_bytes()
        if digest(source) != record['source']['state_sha256']:
            raise ValueError('Source uncertainty state changed during owner recovery')
        for name in record['source_dependencies']:
            guard._read(name)
        if not receipts:
            guard.p.store.event(connection, guard.p.run['id'], _EVENT, receipt)


def recover_null_owner_resolution(guard):
    """Return a verified frozen replay, or None when the defect is out of scope.

    Only a resolved, dependency-free item that redundantly names its actual
    cited current unit may recover its authoritative null owner.  Open items,
    repair permissions, conclusions and evidence are never rewritten.
    """
    from .uncertainty_review import (UncertaintyAssessment, declared_doubts,
                                    effective_uncertainty_issues,
                                    validate_uncertainty_assessment)
    try:
        if not guard.path.exists():
            if guard.state is not None or (guard.folder.exists() and any(guard.folder.iterdir())):
                raise ValueError('Owner recovery source state is missing beside retained evidence')
            return None
        source_raw = guard.path.read_bytes()
        saved_state = json.loads(source_raw)
        if saved_state.get('status') != 'INVALID':
            return None
        if saved_state.get('migration_source'):
            raise ValueError('Owner recovery cannot mutate or reinterpret a pending migration')
        guard._load()
        state = guard.state
        if (json.loads(source_raw) != state or state['identity'] != guard.identity
                or state['identity_hash'] != guard.key or digest(state['identity']) != guard.key):
            raise ValueError('Uncertainty owner-recovery source identity changed')
        calls = state['calls']
        if type(calls) is not int or calls < 1:
            raise ValueError('Invalid saved uncertainty call count')
        failure_name = 'failure-' + str(calls) + '.json'
        failure = guard._read(failure_name)
        if (failure['code'] is not None or failure.get('message') != _OWNER_ERROR
                or failure.get('retryable_same_slot') is not False):
            return None
        response_name = 'response-' + str(calls) + '.json'
        if state.get('response_file') != response_name:
            raise ValueError('Owner failure lacks its exact saved response slot')
        context = guard._read('input.json')
        ordinary_context = guard._read('ordinary-context.json')
        ordinary = guard._read('ordinary-review.json')
        assessment_input = guard._read('assessment-input.json')
        response = guard._read(response_name)
        if (context != guard.context or context['declared_doubts'] != declared_doubts(context['section'])
                or assessment_input != {**context, 'ordinary_review': ordinary}):
            raise ValueError('Owner recovery input differs from its authoritative frozen context')
        # Verify the ordinary review without re-running it or erasing any issue.
        checked = MathReview.model_validate(ordinary).model_dump()
        actual = {unit['id'] for unit in context['section']['units']}
        if (checked != ordinary or set(checked['checked_unit_ids']) != actual
                or any(issue['unit_id'] not in actual for issue in checked['issues'])):
            raise ValueError('Owner recovery ordinary-review scope is invalid')
        if not isinstance(ordinary_context, dict):
            raise ValueError('Owner recovery ordinary context is invalid')
        try:
            normalized = UncertaintyAssessment.model_validate(response).model_dump()
        except ValueError:
            return None
        if normalized != response:
            return None
        expected = {item['uncertainty_id']: item for item in context['declared_doubts']}
        ids = [item['uncertainty_id'] for item in normalized['items']]
        if len(ids) != len(set(ids)) or set(ids) != set(expected):
            return None
        changes = []
        for index, item in enumerate(normalized['items']):
            declared = expected[item['uncertainty_id']]
            if item['unit_id'] == declared['unit_id']:
                continue
            cited_owner = item['unit_id']
            if (declared['unit_id'] is not None or cited_owner not in actual
                    or item['disposition'] != 'resolved_by_current_body'
                    or item['remaining_dependency'] is not False
                    or item['repair_instruction'] is not None or not item['evidence']
                    or any(e['source_key'] != 'current:' + cited_owner for e in item['evidence'])):
                return None
            changes.append({'item_index': index, 'uncertainty_id': item['uncertainty_id'],
                            'field': 'unit_id', 'original_value': cited_owner,
                            'authoritative_value': None})
            item['unit_id'] = None
        if not changes:
            return None
        try:
            assessment = validate_uncertainty_assessment(normalized, context)
        except ValueError:
            return None
        contract = {'version': 1, 'helper_sha256': digest(Path(__file__).read_bytes()),
                    'operation': 'restore_null_owner_for_resolved_current_evidence'}
        source = {'state_key': guard.path.relative_to(guard.p.settings.workspace).as_posix(),
                  'state_sha256': digest(source_raw), 'identity_hash': guard.key,
                  'response_file': response_name,
                  'response_sha256': state['dependencies'][response_name],
                  'failure_file': failure_name,
                  'failure_sha256': state['dependencies'][failure_name]}
        identity = {'source': source, 'contract': contract}
        key = digest(identity)
        record = {'schema_version': 1, 'identity': identity, 'identity_hash': key,
                  'source': source, 'source_dependencies': copy.deepcopy(state['dependencies']),
                  'original_response': copy.deepcopy(response), 'field_changes': changes,
                  'normalized_response': normalized, 'assessment': assessment,
                  'validation': {'status': 'PASS', 'validator': 'validate_uncertainty_assessment',
                                 'assessment_hash': digest(assessment)},
                  'status': 'REVIEWED_PROTOCOL_RECOVERED', 'provider_calls_during_replay': 0,
                  'teacher_review': 'NOT_RUN'}
        folder = Path(guard.p.root) / 'uncertainty-owner-recovery' / guard.key[:24]
        if not folder.resolve().is_relative_to(Path(guard.p.root).resolve()):
            raise ValueError('Owner-recovery evidence escaped the controlled run')
        path = folder / 'recovery.json'
        record_sha = digest(_record_bytes(record))
        evidence_key = path.relative_to(guard.p.settings.workspace).as_posix()
        receipt = {'identity_hash': key, 'source_identity_hash': guard.key,
                   'source_state_sha256': source['state_sha256'],
                   'evidence_key': evidence_key, 'evidence_sha256': record_sha,
                   'provider_calls_during_replay': 0, 'teacher_review': 'NOT_RUN'}
        _persist(guard, path, record, receipt)
        report = {'identity_hash': key, 'assessment': assessment,
                  'status': 'REVIEWED_PROTOCOL_RECOVERED', 'source_identity_hash': guard.key,
                  'source_state_sha256': source['state_sha256'],
                  'evidence_key': evidence_key, 'evidence_sha256': record_sha,
                  'provider_calls_during_replay': 0, 'teacher_review': 'NOT_RUN'}
        return report, effective_uncertainty_issues(context['section'], assessment)
    except AgentError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AgentError('UNCERTAINTY_EVIDENCE_BLOCKED', str(exc)) from None
