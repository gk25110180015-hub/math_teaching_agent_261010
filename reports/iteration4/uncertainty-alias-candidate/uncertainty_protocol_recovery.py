"""Narrow syntax recovery and replay of one deployed uncertainty contract.

No model calls, mathematical decisions or old evidence edits occur here.
"""
import copy
import json
from pathlib import Path

from .util import canonical, digest, within


LEGACY_CONTRACT = {
    'version': 1,
    'helper_sha256': '288a374421c952020165b4ec12585e98e4dc5948dacad3d49df759e342f632e2',
    'prompt_sha256': '5c0f40881c0ef1be2c5c26d1e67865280ee0b7ddd3bcb2b2bc6ebfab77a28c39',
    'schema_sha256': '17483c3498be1c224aa33dee7db98ac074bc8c0cb8b2ff22c7545c03d1135b40',
    'ordinary_prompt_sha256': 'cd75bbcf1516a0fa5ecaa882e753956e82d65da7e0640442db98717a1cf6f92d',
    'ordinary_schema_sha256': 'e116894cd37689f5f569ba9fd2873ff2f5e058ee98733ee5ce8c517fb99b2b5f',
    'attribution_contract': {
        'version': 1,
        'helper_sha256': '078a3fe47159d8934b71b30df7d4940742a9b53ba2fbe0f3d0ab66b249377da5',
        'reviewer_prompt_sha256': 'cd75bbcf1516a0fa5ecaa882e753956e82d65da7e0640442db98717a1cf6f92d',
        'adjudicator_prompt_sha256': '0e2e9c9568299b12597b2a6637d5d043eb13f63c3e28702d8370b212958fc65b',
        'adjudication_schema_sha256': '449eec8e6f12dedbf899e88ad4189caac019d6fb3f1c34415f39e516853a85d8'},
    'provider_sha256': '556b85726acc7f11318dd6aa21a2e7e2a304f5c5d7c78ecb89adaec72db372d6'}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key is not recoverable')
        result[key] = value
    return result


def decode_uncertainty_json(text):
    """Only complete objects followed by at most four stray closers recover.

    Duplicate keys, non-finite literals, partial objects, extra objects and
    prose are rejected. The returned object is never repaired or reworded.
    """
    if not isinstance(text, str) or len(text) > 8 * 1024 * 1024:
        raise ValueError('Invalid or oversized uncertainty response')
    document = text.strip()
    if document.startswith('```') and document.endswith('```'):
        document = '\n'.join(document.splitlines()[1:-1]).strip()
    def bad_constant(value):
        raise ValueError('Nonfinite JSON number is not permitted')
    decoder = json.JSONDecoder(object_pairs_hook=_unique_pairs, parse_constant=bad_constant)
    value, end = decoder.raw_decode(document)
    if not isinstance(value, dict):
        raise ValueError('Expected one uncertainty JSON object')
    suffix = document[end:]
    if not suffix.strip():
        return value, None
    closers = ''.join(suffix.split())
    if len(suffix) > 32 or not 1 <= len(closers) <= 4 or any(c not in ']}' for c in closers):
        raise ValueError('Uncertainty response has ambiguous trailing data')
    return value, {'protocol_version': 1, 'kind': 'bounded_trailing_closers',
        'original_sha256': digest(text), 'object_end': end,
        'removed_suffix': suffix, 'output_hash': digest(value)}


def _events(pipeline):
    with pipeline.store.connect() as connection:
        return [dict(row) for row in connection.execute(
            'SELECT sequence,type,payload_json,timestamp FROM events WHERE run_id=? ORDER BY sequence',
            (pipeline.run['id'],))]


def _verified_call(events, state, assessment_input, result=None):
    from .provider import PROMPTS
    from .uncertainty_review import UncertaintyAssessment
    instruction = (PROMPTS / 'reviewer_uncertainty.md').read_text(encoding='utf-8')
    if digest(instruction) != LEGACY_CONTRACT['prompt_sha256'] or digest(UncertaintyAssessment.model_json_schema()) != LEGACY_CONTRACT['schema_sha256']:
        raise ValueError('Legacy response prompt/schema cannot be reinterpreted')
    messages = [{'role': 'system', 'content': instruction + '\n必须只输出一个 JSON 对象，精确遵循 schema：\n' + canonical(UncertaintyAssessment.model_json_schema())},
        {'role': 'user', 'content': 'UNTRUSTED_SOURCE_DATA\n' + canonical(assessment_input) + '\nEND_UNTRUSTED_SOURCE_DATA'}]
    input_hash = digest(messages)
    selected = []
    for row in events:
        payload = json.loads(row['payload_json'])
        if payload.get('role') != 'reviewer_uncertainty':
            continue
        if not state['started_at'] <= row['timestamp'] <= state['_failure_at']:
            continue
        if payload.get('prompt_hash') != LEGACY_CONTRACT['prompt_sha256'] or payload.get('schema_hash') != LEGACY_CONTRACT['schema_sha256']:
            continue
        selected.append((row, payload))
    requests = [(row, payload) for row, payload in selected if row['type'] == 'provider.request' and payload.get('input_hash') == input_hash]
    candidates = []
    for request, payload in requests:
        call = payload.get('call_id')
        if not call:
            continue
        call_rows = [(row, item) for row, item in selected if item.get('call_id') == call and row['sequence'] >= request['sequence']]
        if any(any(item.get(key) != payload.get(key) for key in ('model_id', 'model', 'base_url', 'preferred_model_id'))
               for _, item in call_rows):
            continue
        success = [(row, item) for row, item in call_rows if row['type'] == 'provider.result'
            and item.get('transport_status') == 'SUCCESS' and item.get('http_status') == 200
            and item.get('input_hash') == input_hash
            and (not item.get('streaming') or (item.get('stream_complete') is True and item.get('finish_reason') == 'stop'))]
        if len(success) != 1:
            continue
        outcomes = [(row, item) for row, item in call_rows if row['type'] == 'provider.result'
            and item.get('schema_attempt') == 1 and row['sequence'] > success[0][0]['sequence']
            and result is not None and item.get('output_hash') == digest(result)]
        if result is None:
            outcomes = [(row, item) for row, item in call_rows if row['type'] == 'provider.result'
                and item.get('schema_attempt') == 1 and row['sequence'] > success[0][0]['sequence']
                and item.get('invalid_response_archive') and len(item.get('validation_errors', [])) == 1
                and item['validation_errors'][0].get('type') == 'invalid_json'
                and item['validation_errors'][0].get('message') == 'Extra data']
        if len(outcomes) == 1:
            candidates.append((request, success[0][0], outcomes[0][0], outcomes[0][1]))
    if len(candidates) != 1:
        raise ValueError('Saved uncertainty response lacks one exact request/outcome chain')
    return candidates[0]


def legacy_replay(guard, expected_source=None):
    """Validate a known INVALID predecessor; return frozen replay materials."""
    from .domain import MathReview
    from .uncertainty_review import validate_uncertainty_assessment
    base = guard.folder.parent
    matches = []
    if not base.exists():
        return None
    for folder in base.iterdir():
        if not folder.is_dir() or folder == guard.folder:
            continue
        if not folder.resolve().is_relative_to(base.resolve()):
            raise ValueError('Uncertainty evidence folder escaped its controlled root')
        path = folder / 'state.json'
        if not path.exists():
            if (folder / 'input.json').exists() and json.loads((folder / 'input.json').read_bytes()) == guard.context:
                raise ValueError('Missing prior state beside the same frozen uncertainty input')
            continue
        state = json.loads(path.read_bytes())
        identity = state.get('identity', {})
        if identity.get('context_hash') != guard.identity['context_hash'] or identity.get('plan_hash') != guard.identity['plan_hash'] or identity.get('plan_revision') != guard.identity['plan_revision']:
            continue
        matches.append((path, state))
    if not matches:
        if expected_source:
            raise ValueError('Recorded legacy uncertainty source disappeared')
        return None
    roots = [(path, state) for path, state in matches
             if state.get('identity', {}).get('contract') == LEGACY_CONTRACT]
    if len(roots) != 1:
        raise ValueError('Ambiguous prior uncertainty verdicts for the same mathematical input')
    path, state = roots[0]
    legacy = _replay_invalid(guard, path, state, expected_source)
    for other_path, other_state in matches:
        if other_path != path:
            _verify_migration_alias(guard, other_path, other_state, legacy)
    return legacy


def _verify_migration_alias(guard, path, state, legacy):
    # Only the two precisely known deployments differed in SSE API-error
    # transport handling. No arbitrary policy versions or new calls fold in.
    contract = {**copy.deepcopy(LEGACY_CONTRACT), 'version': 2,
        'helper_sha256': '2014e3aec411c6aced3fe0f16e38323397bbd9b5a44e0841fe1a800157511187',
        'protocol_recovery_sha256': 'fcb647c4ba2d5cfbda92485ba9a6d284eed9e4ab611f0117a76baf231d77cd15'}
    known = [{**contract, 'provider_sha256': value} for value in (
        'adaac69a8e12ff4956a8b251170176ab3cae80da787bd7f76bd729f116303685',
        '529a8c3baf3f660d503757302534caa0f89a3cdb18b7bd31b0ddf7a5dc124c79')]
    if (state.get('schema_version') != 1 or state.get('identity', {}).get('contract') not in known
            or state.get('status') != 'REVIEWED' or state.get('calls') != 1
            or state.get('provider_calls_during_replay') != 0
            or state.get('migration_source') != legacy['source']
            or state.get('origin_job_id') != legacy['origin_job_id']
            or state.get('response_file') != 'response-1.json'):
        raise ValueError('Additional uncertainty verdict is not a known completed migration alias')
    if digest(state['identity']) != state.get('identity_hash') or path.parent.name != state['identity_hash'][:24]:
        raise ValueError('Migration alias identity SHA mismatch')
    expected = {'input.json': guard.context, 'migration.json': legacy['provenance'],
        **{name: legacy[name] for name in ('ordinary-context.json', 'ordinary-review.json',
            'assessment-input.json', 'response-1.json', 'assessment.json')}}
    if set(state['dependencies']) != set(expected):
        raise ValueError('Migration alias has missing or unexpected evidence')
    for name, value in expected.items():
        raw = within(path.parent, name).read_bytes()
        if digest(raw) != state['dependencies'][name] or json.loads(raw) != value:
            raise ValueError('Migration alias evidence differs from original replay')
    receipt = {'identity_hash': state['identity_hash'], 'source': legacy['source'],
        'evidence_key': path.relative_to(guard.p.settings.workspace).as_posix(),
        'migration_sha256': state['dependencies']['migration.json'],
        'provider_calls_during_replay': 0, 'teacher_review': 'NOT_RUN'}
    found = [json.loads(row['payload_json']) for row in _events(guard.p)
        if row['type'] == 'math.uncertainty_migrated'
        and json.loads(row['payload_json']).get('identity_hash') == state['identity_hash']]
    if found != [receipt]:
        raise ValueError('Migration alias lacks its unique exact audit receipt')


def _replay_invalid(guard, path, state, expected_source):
    # The original strict replay checks remain unchanged below this boundary.
    from .domain import MathReview
    from .uncertainty_review import validate_uncertainty_assessment
    if any(guard.identity['contract'].get(key) != LEGACY_CONTRACT[key] for key in (
            'prompt_sha256', 'schema_sha256', 'ordinary_prompt_sha256', 'ordinary_schema_sha256', 'attribution_contract')):
        raise ValueError('Changed mathematical review rules cannot reuse the legacy judgment')
    source = {'state_key': path.relative_to(guard.p.settings.workspace).as_posix(), 'state_sha256': digest(path.read_bytes()),
        'identity_hash': state.get('identity_hash')}
    if expected_source is not None and source != expected_source:
        raise ValueError('Frozen legacy source identity or bytes changed')
    if state.get('schema_version') != 1 or state.get('identity', {}).get('contract') != LEGACY_CONTRACT or state.get('status') != 'INVALID' or state.get('calls') != 1:
        raise ValueError('Only the exact deployed INVALID uncertainty contract may migrate')
    if digest(state['identity']) != state['identity_hash'] or path.parent.name != state['identity_hash'][:24]:
        raise ValueError('Legacy uncertainty identity hash mismatch')
    data = {}
    for name, sha in state['dependencies'].items():
        if Path(name).name != name:
            raise ValueError('Legacy evidence name escaped its folder')
        evidence_path = within(path.parent, name)
        raw = evidence_path.read_bytes()
        if digest(raw) != sha:
            raise ValueError('Legacy evidence SHA mismatch')
        data[name] = json.loads(raw)
    if data['input.json'] != guard.context or data['assessment-input.json'] != {**guard.context, 'ordinary_review': data['ordinary-review.json']}:
        raise ValueError('Legacy body, plan or assessment input changed')
    review = MathReview.model_validate(data['ordinary-review.json']).model_dump()
    actual = {unit['id'] for unit in guard.context['section']['units']}
    if review != data['ordinary-review.json'] or set(review['checked_unit_ids']) != actual or any(issue['unit_id'] not in actual for issue in review['issues']):
        raise ValueError('Legacy ordinary review has invalid scope')
    failure = data['failure-1.json']
    if failure['retryable_same_slot'] is not False:
        raise ValueError('Migration only revalidates completed verdicts')
    events = _events(guard.p)
    receipts = [row for row in events if row['type'] == 'math.uncertainty_reviewed' and (lambda item:
        item.get('identity_hash') == state['identity_hash'] and item.get('evidence_sha256') == source['state_sha256']
        and item.get('evidence_key') == source['state_key'] and item.get('status') == 'INVALID'
        and item.get('plan_hash') == guard.identity['plan_hash'] and item.get('plan_revision') == guard.identity['plan_revision']
        and item.get('origin_job_id') == state['origin_job_id'])(json.loads(row['payload_json']))]
    if not receipts:
        raise ValueError('Legacy INVALID state lacks its exact persisted audit receipt')
    call_state = {**state, '_failure_at': failure['at']}
    recovery = None
    if state.get('response_file'):
        if state['response_file'] != 'response-1.json' or failure['code'] is not None or failure['message'] != 'Resolving or repairing a doubt needs actual target evidence':
            raise ValueError('Legacy saved-response failure is outside the narrow migration')
        response = data['response-1.json']
        if not any(item.get('unit_id') is None and item.get('disposition') == 'resolved_by_current_body' for item in response['items']):
            raise ValueError('Legacy response does not contain the corrected null-owner resolution case')
        chain = _verified_call(events, call_state, data['assessment-input.json'], response)
    else:
        if failure['code'] != 'INVALID_MODEL_JSON' or 'Extra data' not in failure['message']:
            raise ValueError('Legacy parser failure is outside the narrow migration')
        chain = _verified_call(events, call_state, data['assessment-input.json'])
        metadata = chain[3]
        archive = Path(metadata['invalid_response_archive']).resolve()
        if not archive.is_relative_to((guard.p.build_root / 'provider-failures').resolve()):
            raise ValueError('Legacy response archive escaped the actual run')
        raw = archive.read_bytes()
        if digest(raw) != metadata.get('archive_sha256') or len(raw) != metadata.get('archive_bytes') or digest(raw) != metadata.get('invalid_response_hash'):
            raise ValueError('Legacy archive was changed, truncated or redacted semantically')
        response, recovery = decode_uncertainty_json(raw.decode('utf-8'))
        if recovery is None:
            raise ValueError('Legacy archive does not contain the supported trailing-closer defect')
        recovery['archive_key'] = archive.relative_to(guard.p.settings.workspace).as_posix()
        recovery['archive_sha256'] = digest(raw)
    assessed = validate_uncertainty_assessment(response, guard.context)
    provenance = {'source': source, 'source_dependencies': copy.deepcopy(state['dependencies']),
        'source_contract': copy.deepcopy(LEGACY_CONTRACT), 'audit_receipt_sequence': receipts[-1]['sequence'],
        'provider_events': [{**row, 'record_sha256': digest(row)} for row in chain[:3]],
        'provider_calls_during_replay': 0, 'syntax_recovery': recovery,
        'response_hash': digest(response), 'assessment_hash': digest(assessed)}
    return {'source': source, 'provenance': provenance, 'ordinary-context.json': data['ordinary-context.json'],
        'ordinary-review.json': review, 'assessment-input.json': data['assessment-input.json'],
        'response-1.json': response, 'assessment.json': assessed, 'origin_job_id': state['origin_job_id']}
