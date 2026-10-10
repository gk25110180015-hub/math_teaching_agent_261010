"""Explicit migration of the one deployed full-section repair contract to patches."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .domain import WrittenSection
from .local_patch import LocalPatch
from .util import AgentError, canonical, digest, now, uid, within


LEGACY_CONTRACT = {
    'repair_prompt_hash': '46c1ff3b8ea3f0fba7afe1f6a3b99f3286324551522140dc61d8b646807759f9',
    'written_schema_hash': '4e9b07e27f359212c0460381e3cbd6e548d18a48490e553e60b0c56d30d9ada7',
    'normalizer_hash': '25d2fff448b21fcad71b5e7aae512cf6ab27f66bdeefd9e459ca57652a1fd74c',
}
MIGRATION_ID = 'known_full_section_v1_to_strict_patch_v2'
EVENT = 'global.repair_contract_migrated'


def patch_identity(pipeline, plan):
    from .provider import PROMPTS
    from .calculation_protocol import calculation_protocol
    return {
        'plan_hash': plan['hash'], 'model': pipeline.preferred_model_name,
        'provider': pipeline.run['input']['provider'], 'repair_contract_version': 2,
        'repair_prompt_hash': digest((PROMPTS / 'repair_local_patch.md').read_bytes()),
        'written_schema_hash': digest(WrittenSection.model_json_schema()),
        'patch_schema_hash': digest(LocalPatch.model_json_schema()),
        'patch_validator_hash': digest(Path(__file__).with_name('local_patch.py').read_bytes()),
        'calculation_protocol_hash': digest(calculation_protocol()),
        'normalizer_hash': digest(Path(__file__).with_name('lecture_fragments.py').read_bytes()),
        'migration_contract_hash': digest(Path(__file__).read_bytes()),
    }


def known_legacy_identity(pipeline, plan):
    return {'plan_hash': plan['hash'], 'model': pipeline.preferred_model_name,
            'provider': pipeline.run['input']['provider'], **LEGACY_CONTRACT}


def _error():
    return AgentError('GLOBAL_REPAIR_MIGRATION_INVALID',
        '全局修复迁移证据、状态或批准计划无法核实；保留原状态，不清零、不接受旧提案。')


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')


def _immutable(path, data):
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise _error()
        return
    temporary = path.with_name('.' + uid()[:12] + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def _replace_state(path, data):
    temporary = path.with_name('.' + uid()[:12] + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def _unchanged_payload(state):
    return {key: value for key, value in state.items()
            if key not in ('schema_version', 'identity', 'contract_migration')}


def _validate_state(pipeline, plan, state):
    if (type(state.get('schema_version')) is not int
            or state['schema_version'] not in (1, 2)
            or type(state.get('rounds_used')) is not int or state['rounds_used'] < 0
            or state.get('phase') not in ('not_started', 'repair_pending', 'checking', 'validated', 'budget_exhausted')
            or not isinstance(state.get('sections'), dict) or not isinstance(state.get('pending'), list)):
        raise ValueError('Invalid version, round count, phase or collection')
    specs = {spec['id']: spec for spec in plan['sections']}
    if len(specs) != len(plan['sections']) or not set(state['sections']).issubset(specs):
        raise ValueError('Unknown section')
    sections = pipeline._global_repair_sections(state)
    if state['sections'] or state['pending']:
        folder = within(pipeline.settings.workspace, state['round_directory'])
        if folder.parent != (pipeline.root / 'global-repairs').resolve() or not folder.is_dir():
            raise ValueError('Uncontrolled repair directory')
        for record in state['sections'].values():
            if set(record) != {'candidate_key', 'candidate_hash'}:
                raise ValueError('Unexpected candidate record')
            if not within(pipeline.settings.workspace, record['candidate_key']).is_relative_to(folder):
                raise ValueError('Candidate outside its preserved round')
    if state['phase'] in ('not_started', 'checking', 'validated', 'budget_exhausted') and state['pending']:
        raise ValueError('Pending proposal is inconsistent with phase')
    if state['phase'] == 'not_started' and (state['rounds_used'] or state['sections']):
        raise ValueError('Fresh state cannot contain an accepted repair')
    if state['phase'] in ('repair_pending', 'checking') and not state['rounds_used']:
        raise ValueError('Repair state lost its round count')
    all_ids = [unit['id'] for section in sections.values() for unit in section['units']]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError('Ambiguous preserved units')
    pending_ids = set()
    issues = state.get('issues', [])
    if not isinstance(issues, list) or any(not isinstance(issue, dict) for issue in issues):
        raise ValueError('Invalid original concerns')
    for request in state['pending']:
        if not isinstance(request, dict) or set(request) != {'section_id', 'issues', 'allowed_unit_ids', 'neighbors'}:
            raise ValueError('Invalid pending proposal')
        sid = request['section_id']
        if sid not in sections or sid in pending_ids:
            raise ValueError('Unknown or duplicate pending section')
        pending_ids.add(sid)
        allowed = request['allowed_unit_ids']
        if (not isinstance(allowed, list) or not allowed or any(not isinstance(value, str) for value in allowed)
                or len(set(allowed)) != len(allowed)
                or not set(allowed).issubset(unit['id'] for unit in sections[sid]['units'])):
            raise ValueError('Invalid pending allowed units')
        pending_issues = request['issues']
        if (not isinstance(pending_issues, list) or not pending_issues
                or any(not isinstance(issue, dict) or issue.get('severity') not in ('blocking', 'review')
                       for issue in pending_issues)
                or set(allowed) != {issue.get('unit_id') for issue in pending_issues}
                or any(issue not in issues for issue in pending_issues)):
            raise ValueError('Pending scope does not match the preserved concerns')
        if not isinstance(request['neighbors'], list):
            raise ValueError('Invalid neighbor context')
        position = list(specs).index(sid)
        seen = set()
        for neighbor in request['neighbors']:
            if not isinstance(neighbor, dict) or set(neighbor) != {'section', 'generated'}:
                raise ValueError('Invalid neighbor entry')
            other = neighbor['section']['id']
            if (other not in specs or other in seen or neighbor['section'] != specs[other]
                    or abs(list(specs).index(other) - position) != 1):
                raise ValueError('Neighbor is not the approved adjacent section')
            seen.add(other)
            if WrittenSection.model_validate(neighbor['generated']).section_id != other:
                raise ValueError('Neighbor body identity mismatch')
    return sections


def _approved(pipeline, plan, connection):
    run = pipeline.store.row(connection, pipeline.run['id'])
    current = pipeline.store.current_plan(connection, run)
    approval = connection.execute('SELECT * FROM approvals WHERE run_id=? AND revision=? AND hash=?',
        (run['id'], plan['revision'], plan['hash'])).fetchone()
    if (not current or current != plan or current['hash'] != plan['hash'] or current['revision'] != plan['revision']
            or not approval or approval['input_hash'] != run['input_hash']
            or run['input_hash'] != pipeline.run['input_hash']):
        raise _error()
    return run, dict(approval)


def _evidence(pipeline, state, plan, identity):
    marker = state['contract_migration']
    if not isinstance(marker, dict) or set(marker) != {'id', 'evidence_key'}:
        raise _error()
    path = within(pipeline.settings.workspace, marker['evidence_key'])
    parent = pipeline.root / 'global-repairs' / 'contract-migrations'
    if not path.is_relative_to(parent.resolve()) or path.name != 'evidence.json':
        raise _error()
    evidence = json.loads(path.read_bytes())
    old_bytes = (path.parent / 'before.json').read_bytes()
    after_bytes = (path.parent / 'after.json').read_bytes()
    old, after = json.loads(old_bytes), json.loads(after_bytes)
    expected_id = digest([MIGRATION_ID, pipeline.run['id'], digest(old_bytes), identity])
    if (evidence['id'] != marker['id'] or marker['id'] != expected_id or evidence['migration'] != MIGRATION_ID
            or evidence['run_id'] != pipeline.run['id'] or evidence['plan_hash'] != plan['hash']
            or evidence['plan_revision'] != plan['revision']
            or evidence['before_sha256'] != digest(old_bytes) or evidence['after_sha256'] != digest(after_bytes)
            or old['identity'] != known_legacy_identity(pipeline, plan) or old['schema_version'] != 1
            or after['identity'] != identity or after['schema_version'] != 2
            or after['contract_migration'] != marker or state['identity'] != identity
            or _unchanged_payload(old) != _unchanged_payload(after)
            or evidence['preserved_payload_hash'] != digest(_unchanged_payload(old))
            or evidence['from_identity'] != old['identity'] or evidence['to_identity'] != identity
            or evidence['phase_preserved'] != old['phase'] or evidence['rounds_used_preserved'] != old['rounds_used']
            or evidence['pending_scope'] != [{'section_id': item['section_id'], 'allowed_unit_ids': item['allowed_unit_ids']}
                                             for item in old['pending']]
            or type(evidence['request_count_preserved']) is not int or evidence['request_count_preserved'] < 0
            or evidence['evidence_key'] != marker['evidence_key']
            or within(pipeline.settings.workspace, evidence['before_key']) != path.parent / 'before.json'
            or within(pipeline.settings.workspace, evidence['after_key']) != path.parent / 'after.json'
            or evidence['teacher_review'] != 'NOT_RUN'):
        raise _error()
    _validate_state(pipeline, plan, old)
    _validate_state(pipeline, plan, after)
    return evidence, after_bytes


def resume_migration_audit(pipeline, plan, state, identity):
    """Repair only the audit gap after an atomic state write and DB rollback."""
    try:
        _validate_state(pipeline, plan, state)
        if 'contract_migration' not in state:
            return state
        evidence, after_bytes = _evidence(pipeline, state, plan, identity)
        if state['rounds_used'] < evidence['rounds_used_preserved']:
            raise _error()
        with pipeline.store.transaction() as connection:
            pipeline.store.assert_fence(connection, pipeline.job)
            run, approval = _approved(pipeline, plan, connection)
            if (evidence['approval_hash'] != digest(approval) or evidence['input_hash'] != run['input_hash']
                    or type(evidence['request_count_preserved']) is not int
                    or evidence['request_count_preserved'] > run['request_count']):
                raise _error()
            rows = connection.execute('SELECT payload_json FROM events WHERE run_id=? AND type=?',
                (pipeline.run['id'], EVENT)).fetchall()
            matching = [json.loads(row[0]) for row in rows if json.loads(row[0]).get('id') == evidence['id']]
            if matching:
                if len(matching) != 1 or matching[0] != evidence:
                    raise _error()
            else:
                if (pipeline.root / 'global-repair-state.json').read_bytes() != after_bytes:
                    raise _error()
                pipeline.store.event(connection, pipeline.run['id'], EVENT, evidence)
    except (OSError, ValueError, KeyError, TypeError):
        raise _error() from None
    return state


def migrate_known_v1(pipeline, plan, state, identity):
    """Return None for any unknown contract; no broad compatibility fallback."""
    if (type(state.get('schema_version')) is not int or state['schema_version'] != 1
            or state.get('identity') != known_legacy_identity(pipeline, plan)
            or any(identity.get(key) != LEGACY_CONTRACT[key] for key in ('written_schema_hash', 'normalizer_hash'))):
        return None
    try:
        if 'contract_migration' in state:
            raise ValueError('Legacy state cannot already claim migration')
        _validate_state(pipeline, plan, state)
        path = pipeline.root / 'global-repair-state.json'
        before_bytes = path.read_bytes()
        if json.loads(before_bytes) != state:
            raise ValueError('State changed before migration')
        migration_id = digest([MIGRATION_ID, pipeline.run['id'], digest(before_bytes), identity])
        folder = pipeline.root / 'global-repairs' / 'contract-migrations' / migration_id[:24]
        evidence_key = (folder / 'evidence.json').relative_to(pipeline.settings.workspace).as_posix()
        after = copy.deepcopy(state)
        after.update(schema_version=2, identity=identity,
            contract_migration={'id': migration_id, 'evidence_key': evidence_key})
        after_bytes = _bytes(after)
        with pipeline.store.transaction() as connection:
            pipeline.store.assert_fence(connection, pipeline.job)
            run, approval = _approved(pipeline, plan, connection)
            if path.read_bytes() != before_bytes:
                raise _error()
            folder.mkdir(parents=True, exist_ok=True)
            _immutable(folder / 'before.json', before_bytes)
            _immutable(folder / 'after.json', after_bytes)
            if (folder / 'evidence.json').exists():
                evidence, saved_after = _evidence(pipeline, after, plan, identity)
                if saved_after != after_bytes:
                    raise _error()
            else:
                evidence = {
                    'schema_version': 1, 'id': migration_id, 'migration': MIGRATION_ID,
                    'run_id': run['id'], 'job_id': pipeline.job['id'], 'created_at': now(),
                    'plan_hash': plan['hash'], 'plan_revision': plan['revision'],
                    'input_hash': run['input_hash'], 'approval_hash': digest(approval),
                    'request_count_preserved': run['request_count'],
                    'rounds_used_preserved': state['rounds_used'], 'phase_preserved': state['phase'],
                    'pending_scope': [{'section_id': item['section_id'], 'allowed_unit_ids': item['allowed_unit_ids']}
                                      for item in state['pending']],
                    'before_sha256': digest(before_bytes), 'after_sha256': digest(after_bytes),
                    'preserved_payload_hash': digest(_unchanged_payload(state)),
                    'from_identity': state['identity'], 'to_identity': identity,
                    'before_key': (folder / 'before.json').relative_to(pipeline.settings.workspace).as_posix(),
                    'after_key': (folder / 'after.json').relative_to(pipeline.settings.workspace).as_posix(),
                    'evidence_key': evidence_key, 'teacher_review': 'NOT_RUN',
                }
                _immutable(folder / 'evidence.json', _bytes(evidence))
            if (evidence['approval_hash'] != digest(approval) or evidence['input_hash'] != run['input_hash']
                    or type(evidence['request_count_preserved']) is not int
                    or evidence['request_count_preserved'] > run['request_count']):
                raise _error()
            _replace_state(path, after_bytes)
            pipeline.store.event(connection, run['id'], EVENT, evidence)
        return after
    except (OSError, ValueError, KeyError, TypeError):
        raise _error() from None
