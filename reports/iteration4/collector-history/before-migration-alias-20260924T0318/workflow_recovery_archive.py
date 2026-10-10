"""Read-only recovery evidence: frozen verdict migrations and guided patches.

No Service, Store, worker, model or compiler is instantiated. The legacy replay
validator sees an in-memory SELECT-only view of the already collected events.
"""
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

from math_agent.util import digest
from recovery_evidence_archive import archive, failure, save


class SnapshotEvents:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, parameters):
        if (' '.join(sql.split()) !=
                'SELECT sequence,type,payload_json,timestamp FROM events WHERE run_id=? ORDER BY sequence'
                or parameters != (self.snapshot['run']['id'],)):
            raise ValueError('Archival replay permits only the frozen event SELECT')
        return [{key: row[key] for key in ('sequence', 'type', 'payload_json', 'timestamp')}
                for row in self.snapshot['events']]


def _dependencies(path, scope, folder, expected, record):
    values, raw_values = {}, {}
    for name, sha in expected.items():
        if Path(name).name != name:
            raise ValueError('Dependency filename leaves its ledger')
        raw = archive(path/name, scope, folder/name, sha)
        values[name] = json.loads(raw); raw_values[name] = raw
        record['dependencies'].append({'source': str(path/name), 'archive': str(folder/name), 'sha256': digest(raw)})
    return values, raw_values


def inspect_uncertainty_migrations(workspace, snapshot, output):
    root = (workspace/'runs'/snapshot['run']['id']).resolve()
    records, seen = [], set()
    for event in snapshot['events']:
        if event['type'] != 'math.uncertainty_migrated':
            continue
        record = {'event_sequence': event['sequence'], 'timestamp': event['timestamp'],
            'integrity': 'NOT_CHECKED', 'dependencies': [], 'teacher_review': 'NOT_RUN',
            'current_delivery_body_binding': 'NOT_INFERRED_FROM_THIS_LEDGER'}
        try:
            payload = json.loads(event['payload_json']); record['payload'] = payload
            identity_hash = payload['identity_hash']
            if identity_hash in seen:
                raise ValueError('Duplicate uncertainty migration event')
            seen.add(identity_hash)
            path = (workspace/payload['evidence_key']).resolve()
            if path.name != 'state.json' or path.parent.name != identity_hash[:24]:
                raise ValueError('Migration ledger path and identity disagree')
            folder = output/'uncertainty-migration-evidence'/identity_hash[:24]
            raw = archive(path, root/'uncertainty-reviews', folder/'state.json')
            state = json.loads(raw)
            if (state['identity_hash'] != identity_hash or digest(state['identity']) != identity_hash
                    or state['status'] != 'REVIEWED' or state['migration_source'] != payload['source']
                    or state['provider_calls_during_replay'] != 0 or payload['provider_calls_during_replay'] != 0
                    or state['teacher_review'] != 'NOT_RUN' or payload['teacher_review'] != 'NOT_RUN'
                    or state['dependencies']['migration.json'] != payload['migration_sha256']):
                raise ValueError('Migration event is not bound to the completed frozen replay')
            values, _ = _dependencies(path.parent, path.parent, folder, state['dependencies'], record)
            context = values['input.json']
            if digest(context) != state['identity']['context_hash']:
                raise ValueError('Migrated input changed')
            # This pure validator reconstructs the original prompt/schema/input,
            # verifies one actual request -> complete transport -> output chain,
            # and validates the saved response. Its event source cannot write.
            from math_agent.uncertainty_protocol_recovery import legacy_replay
            from math_agent.uncertainty_review import uncertainty_contract
            if state['identity']['contract'] != uncertainty_contract():
                raise ValueError('Archival replay requires the recorded validator contract')
            pipeline = SimpleNamespace(root=root, run=snapshot['run'], store=SnapshotEvents(snapshot),
                settings=SimpleNamespace(workspace=workspace), build_root=workspace/'b'/snapshot['run']['id'][:16])
            guard = SimpleNamespace(folder=path.parent, identity=state['identity'], context=context, p=pipeline)
            replay = legacy_replay(guard, state['migration_source'])
            if replay is None or replay['provenance'] != values['migration.json']:
                raise ValueError('Migration provenance differs from its exact original call chain')
            for name in ('ordinary-context.json', 'ordinary-review.json', 'assessment-input.json', 'response-1.json', 'assessment.json'):
                if replay[name] != values[name]:
                    raise ValueError('Migrated evidence differs from its frozen source: '+name)
            old_path = (workspace/state['migration_source']['state_key']).resolve()
            old_raw = archive(old_path, root/'uncertainty-reviews', folder/'legacy/state.json',
                              state['migration_source']['state_sha256'])
            old_state = json.loads(old_raw)
            _dependencies(old_path.parent, old_path.parent, folder/'legacy', old_state['dependencies'], record)
            syntax = replay['provenance'].get('syntax_recovery')
            if syntax is not None:
                response_raw = archive(workspace/syntax['archive_key'], pipeline.build_root/'provider-failures',
                                       folder/'legacy/provider-response.txt', syntax['archive_sha256'])
                record['dependencies'].append({'source_key':syntax['archive_key'],
                    'sha256':digest(response_raw), 'archive':str(folder/'legacy/provider-response.txt')})
            record.update(integrity='PASS', state_sha256=digest(raw), source=state['migration_source'],
                assessment=values['assessment.json'], section_hash=digest(context['section']),
                disposition_counts=dict(Counter(item['disposition'] for item in values['assessment.json']['items'])),
                provider_calls_during_collection=0, saved_response_validation='PASS_NO_NEW_MODEL_CALL',
                matches_current_approved_plan=(state['identity']['plan_hash'],state['identity']['plan_revision']) ==
                    (snapshot['plan']['hash'],snapshot['plan']['revision']))
        except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
            failure(record, error)
        records.append(record)
    result = {'records': records, 'all_files_verified': all(r['integrity']=='PASS' for r in records),
        'meaning':'Frozen-response protocol replay only. open_dependency remains open; resolved is neither formal proof nor teacher approval, and is not bound to later delivery by this ledger.'}
    save(output/'uncertainty-migration-evidence.json', result)
    return result


def _bound_file(workspace, root, key, expected, destination, record):
    path = (workspace/key).resolve()
    build = (workspace/'b'/root.name[:16]).resolve()
    scope = root if path.is_relative_to(root) else build
    raw = archive(path, scope, destination, expected)
    record['dependencies'].append({'source_key':key,'sha256':digest(raw),'archive':str(destination)})
    return raw


def inspect_guidance_ledgers(workspace, snapshot, output):
    root = (workspace/'runs'/snapshot['run']['id']).resolve()
    records, seen, applied = [], set(), []
    for event in snapshot['events']:
        if event['type']=='repair.guidance_applied':
            applied.append({'event':event, 'payload':json.loads(event['payload_json'])})
    for event in snapshot['events']:
        if event['type'] != 'repair.guidance_requested':
            continue
        record={'event_sequence':event['sequence'],'timestamp':event['timestamp'],'integrity':'NOT_CHECKED',
            'dependencies':[],'teacher_review':'NOT_RUN','current_delivery_body_binding':'NOT_INFERRED_FROM_THIS_LEDGER'}
        try:
            action=json.loads(event['payload_json']);record['action']=action
            key=(action['job_id'],action['action_id'])
            if key in seen:raise ValueError('Duplicate guidance action')
            seen.add(key)
            request={'expected_plan_revision':action['plan_revision'],'expected_plan_hash':action['plan_hash'],
                'action_id':action['action_id'],'section_id':action['section_id'],
                'expected_candidate_hash':action['candidate_hash'],'unit_ids':action['unit_ids'],
                'instructions':action['instructions'],'source':action['source']}
            if (digest(request)!=action['payload_hash'] or action['teacher_review']!='NOT_RUN'
                    or action['approval_preserved'] is not True or action['actor']!='local_user'
                    or (action['plan_hash'],action['plan_revision'])!=(snapshot['approval']['hash'],snapshot['approval']['revision'])
                    or (action['plan_hash'],action['plan_revision'])!=(snapshot['plan']['hash'],snapshot['plan']['revision'])
                    or not any(job['id']==action['job_id'] and job['kind']=='build' for job in snapshot['jobs'])
                    or type(action['request_count_preserved']) is not int
                    or not 0<=action['request_count_preserved']<=snapshot['run']['request_count']
                    or not 1<=action['budget_version']<=snapshot['budget']['version']):
                raise ValueError('Guidance action lost its request, job, approval or preserved count binding')
            folder=output/'repair-guidance-evidence'/digest(list(key))[:24]
            ledger=root/'repair-guidance'/digest(list(key))[:24]/'state.json'
            original_raw=_bound_file(workspace,root,action['candidate_key'],action['candidate_file_hash'],folder/'original-candidate.json',record)
            from math_agent.domain import WrittenSection
            before=WrittenSection.model_validate(json.loads(original_raw)).model_dump()
            if (digest(before)!=action['candidate_hash'] or before['section_id']!=action['section_id']
                    or not action['unit_ids'] or len(set(action['unit_ids']))!=len(action['unit_ids'])
                    or not set(action['unit_ids']).issubset(unit['id'] for unit in before['units'])):
                raise ValueError('Guidance scope differs from its actual original body')
            matching=[row for row in applied if (row['payload'].get('job_id'),row['payload'].get('action_id'))==key]
            if len(matching)>1:raise ValueError('Duplicate guidance acceptance event')
            binding=action['recovery_binding']
            if not ledger.exists():
                if matching:raise ValueError('Applied guidance is missing its ledger')
                _bound_file(workspace,root,binding['state_key'],binding['state_sha256'],folder/'pending-recovery-state.json',record)
                if binding.get('global_state_key'):
                    _bound_file(workspace,root,binding['global_state_key'],binding['global_state_sha256'],folder/'pending-global-state.json',record)
                record.update(integrity='PASS',phase='REQUESTED_NOT_STARTED',applied_event=None,
                    meaning='Requested only; no generated or accepted patch claimed')
                records.append(record);continue
            raw=archive(ledger,root/'repair-guidance',folder/'state.json');state=json.loads(raw)
            if state['action_hash']!=digest(action) or state['teacher_review']!='NOT_RUN' or state['before_hash']!=digest(before):
                raise ValueError('Guidance ledger differs from its original action')
            values,raw_values=_dependencies(ledger.parent,ledger.parent,folder,state['dependencies'],record)
            if state['phase'] not in ('READY','PROPOSAL_PENDING','APPLYING','APPLIED','REJECTED'):
                raise ValueError('Unknown guidance ledger phase')
            if state['phase']!='READY' and not {'action.json','before.json','recovery-before.json'}.issubset(values):
                raise ValueError('Guidance proposal lost its frozen initialization')
            if 'action.json' in values and values['action.json']!=action:raise ValueError('Saved guidance action changed')
            if 'before.json' in values and values['before.json']!=before:raise ValueError('Saved original guidance body changed')
            if 'recovery-before.json' in values:
                recovery=values['recovery-before.json']
                if (digest(raw_values['recovery-before.json'])!=binding['state_sha256']
                        or recovery['identity']!=binding['identity']
                        or digest(recovery.get('pending_issues',[]))!=binding['pending_issues_sha256']):
                    raise ValueError('Frozen local recovery does not match its submitted raw state')
                for n,item in enumerate(recovery.get('evidence_dependencies',[])):
                    _bound_file(workspace,root,item['key'],item['hash'],folder/'bound-evidence'/('local-'+str(n)+'.bin'),record)
            if binding.get('last_review_key'):
                _bound_file(workspace,root,binding['last_review_key'],binding['last_review_sha256'],folder/'bound-evidence/last-review.json',record)
            if binding.get('global_state_key'):
                if 'global-before.json' not in values:
                    if state['phase']!='READY':raise ValueError('Guidance has no frozen original global state')
                else:
                    if digest(raw_values['global-before.json'])!=binding['global_state_sha256']:
                        raise ValueError('Frozen global state does not match submitted bytes')
                    for sid,item in values['global-before.json'].get('sections',{}).items():
                        _bound_file(workspace,root,item['candidate_key'],item['candidate_hash'],
                                    folder/'bound-evidence'/('global-'+digest(sid)[:12]+'.json'),record)
            if state['phase'] in ('APPLYING','APPLIED') or matching:
                if not {'after.json','proposal.json','patch-evidence.json','normalization.json'}.issubset(values):
                    raise ValueError('Guidance acceptance lost its proposal or output evidence')
                from math_agent.local_patch import apply_local_patch
                from math_agent.lecture_fragments import normalize_written_section
                repaired,patch_evidence=apply_local_patch(before,action['unit_ids'],values['proposal.json'])
                selected={**repaired,'units':[unit for unit in repaired['units'] if unit['id'] in action['unit_ids']]}
                normalized,normalization=normalize_written_section(selected)
                texts={unit['id']:unit['tex'] for unit in normalized['units']}
                for unit in repaired['units']:
                    if unit['id'] in texts:unit['tex']=texts[unit['id']]
                if (repaired!=values['after.json'] or digest(repaired)!=state['after_hash']
                        or patch_evidence!=values['patch-evidence.json'] or normalization!=values['normalization.json']
                        or normalization['status']!='PASS'):
                    raise ValueError('Saved guided output does not reproduce the strictly scoped patch')
                record['saved_patch_replay']='PASS_NO_MODEL_OR_COMPILER_CALL'
            if state['phase']=='APPLIED' and not matching:raise ValueError('Applied ledger lacks its acceptance event')
            if matching:
                accepted=matching[0]['payload']
                if (matching[0]['event']['sequence']<=event['sequence'] or accepted['section_id']!=action['section_id']
                        or accepted['before_hash']!=action['candidate_hash'] or accepted['after_hash']!=state['after_hash']
                        or accepted['unit_ids']!=action['unit_ids'] or accepted['source']!=action['source']
                        or accepted['status']!='UNCHECKED_REPAIRED' or accepted['teacher_review']!='NOT_RUN'):
                    raise ValueError('Guidance acceptance event changed its original scope or meaning')
            record.update(integrity='PASS',phase=state['phase'],state_sha256=digest(raw),
                applied_event=matching[0] if matching else None,proposal_number=state['proposal_number'],
                meaning='APPLIED means a scoped patch was accepted for checking; it is not mathematical or teacher approval.')
        except (OSError,ValueError,KeyError,TypeError,ImportError) as error:
            failure(record,error)
        records.append(record)
    orphans=[row for row in applied if (row['payload'].get('job_id'),row['payload'].get('action_id')) not in seen]
    result={'records':records,'orphan_applied_events':orphans,
        'all_files_verified':not orphans and all(row['integrity']=='PASS' for row in records),
        'meaning':'Requests, exact input bytes, preserved state and scoped patch output are archived. No model, compile, final-body or teacher pass is inferred.'}
    save(output/'repair-guidance-evidence.json',result)
    return result
