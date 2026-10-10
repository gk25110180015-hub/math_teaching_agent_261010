"""Pure read-only archival helpers; no Service/Store/model calls or migration."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from math_agent.util import digest


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def archive(source,scope,target,expected=None):
    source=source.resolve()
    if not source.is_relative_to(scope.resolve()):
        raise ValueError('Recovery evidence leaves its task directory')
    raw=source.read_bytes();target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and target.read_bytes()!=raw:
        raise ValueError('Refusing to overwrite an archived evidence file')
    if not target.exists():target.write_bytes(raw)
    if expected is not None and digest(raw)!=expected:
        raise ValueError('Recovery dependency SHA changed: '+source.name)
    return raw


def failure(record,error):
    record.update(integrity='UNREADABLE_OR_INVALID',error={'type':type(error).__name__,'message':str(error)})


def inspect_global_migrations(workspace,snapshot,output):
    root=(workspace/'runs'/snapshot['run']['id']).resolve()
    records=[];current=None;current_record={'status':'NOT_PRESENT'}
    path=root/'global-repair-state.json'
    try:
        if path.is_file():
            raw=archive(path,root,output/'global-migration-evidence/current-state.json')
            current=json.loads(raw)
            current_record={'status':'ARCHIVED','sha256':digest(raw),'phase':current.get('phase'),
                'schema_version':current.get('schema_version'),'identity':current.get('identity'),'rounds_used':current.get('rounds_used')}
    except (OSError,ValueError,TypeError) as error:
        current_record={'status':'UNREADABLE_OR_INVALID','error':str(error)}
    seen=set()
    for event in snapshot['events']:
        if event['type']!='global.repair_contract_migrated':continue
        record={'event_sequence':event['sequence'],'timestamp':event['timestamp'],
                'integrity':'NOT_CHECKED','dependencies':[],'teacher_review':'NOT_RUN'}
        try:
            payload=json.loads(event['payload_json']);record['payload']=payload;key=payload['id']
            if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key) or key in seen:
                raise ValueError('Duplicate or invalid migration identity')
            seen.add(key)
            path=(workspace/payload['evidence_key']).resolve();folder=output/'global-migration-evidence'/key[:24]
            raw=archive(path,root/'global-repairs/contract-migrations',folder/'evidence.json')
            if json.loads(raw)!=payload:raise ValueError('Migration journal differs from its event')
            before_raw=archive(workspace/payload['before_key'],path.parent,folder/'before.json',payload['before_sha256'])
            after_raw=archive(workspace/payload['after_key'],path.parent,folder/'after.json',payload['after_sha256'])
            before,after=json.loads(before_raw),json.loads(after_raw)
            kept=lambda value:{k:v for k,v in value.items() if k not in ('identity','schema_version','contract_migration')}
            if (type(before['schema_version']) is not int or before['schema_version']!=1
                    or type(after['schema_version']) is not int or after['schema_version']!=2
                    or kept(before)!=kept(after) or digest(kept(before))!=payload['preserved_payload_hash']
                    or before['identity']!=payload['from_identity'] or after['identity']!=payload['to_identity']
                    or after['contract_migration']!={'id':key,'evidence_key':payload['evidence_key']}
                    or digest([payload['migration'],snapshot['run']['id'],digest(before_raw),after['identity']])!=key
                    or payload['run_id']!=snapshot['run']['id']
                    or payload['plan_hash']!=snapshot['plan']['hash'] or payload['plan_revision']!=snapshot['plan']['revision']
                    or payload['approval_hash']!=digest(snapshot['approval']) or payload['input_hash']!=snapshot['run']['input_hash']
                    or type(payload['request_count_preserved']) is not int
                    or not 0<=payload['request_count_preserved']<=snapshot['run']['request_count']
                    or payload['rounds_used_preserved']!=before['rounds_used'] or payload['phase_preserved']!=before['phase']
                    or payload['pending_scope']!=[{'section_id':p['section_id'],'allowed_unit_ids':p['allowed_unit_ids']} for p in before['pending']]
                    or payload['teacher_review']!='NOT_RUN'):
                raise ValueError('Migration did not preserve its approved state')
            if current and current.get('contract_migration',{}).get('id')==key:
                if (current.get('identity')!=after['identity'] or type(current.get('rounds_used')) is not int
                        or current['rounds_used']<before['rounds_used']):
                    raise ValueError('Current migration state rolled back its contract or rounds')
            for label,state in [('before',before),('after',after),*([('current',current)] if current else [])]:
                for sid,item in state.get('sections',{}).items():
                    target=folder/(label+'-'+digest(sid)[:12]+'-'+item['candidate_hash'][:16]+'.json')
                    data=archive(workspace/item['candidate_key'],root/'global-repairs',target,item['candidate_hash'])
                    if json.loads(data).get('section_id')!=sid:raise ValueError('Candidate section ID changed')
                    record['dependencies'].append({'state':label,'section_id':sid,'source_key':item['candidate_key'],
                        'sha256':digest(data),'archive':str(target)})
            record['integrity']='PASS'
        except (OSError,ValueError,KeyError,TypeError) as error:failure(record,error)
        records.append(record)
    marker=current.get('contract_migration',{}) if isinstance(current,dict) else {}
    bound=not marker or marker.get('id') in seen
    result={'records':records,'current_state':current_record,'current_marker_has_event':bound,
        'all_files_verified':current_record['status']!='UNREADABLE_OR_INVALID' and bound and all(r['integrity']=='PASS' for r in records),
        'meaning':'State/file preservation only; not mathematical proof, new plan approval or teacher review.'}
    save(output/'global-migration-evidence.json',result)
    return result


def inspect_uncertainty_ledgers(workspace,snapshot,output):
    root=(workspace/'runs'/snapshot['run']['id']).resolve();grouped=defaultdict(list)
    for event in snapshot['events']:
        if event['type']=='math.uncertainty_reviewed':
            payload=json.loads(event['payload_json'])
            grouped[(payload.get('identity_hash'),payload.get('evidence_key'))].append(
                {'sequence':event['sequence'],'timestamp':event['timestamp'],'payload':payload})
    records=[]
    for (identity_hash,key),events in grouped.items():
        last=max(events,key=lambda event:event['sequence']);payload=last['payload']
        record={'events':events,'latest_event_sequence':last['sequence'],'identity_hash':identity_hash,
            'evidence_key':key,'integrity':'NOT_CHECKED','dependencies':[],'teacher_review':'NOT_RUN',
            'current_delivery_body_binding':'NOT_INFERRED_FROM_THIS_LEDGER'}
        try:
            if not isinstance(identity_hash,str) or not re.fullmatch('[0-9a-f]{64}',identity_hash) or not isinstance(key,str):
                raise ValueError('Invalid uncertainty identity/key')
            path=(workspace/key).resolve();folder=output/'uncertainty-evidence'/identity_hash[:24]
            raw=archive(path,root/'uncertainty-reviews',folder/'state.json',payload['evidence_sha256'])
            state=json.loads(raw);identity=state['identity'];dependencies={}
            if (digest(identity)!=identity_hash or state['identity_hash']!=identity_hash
                    or state['status']!=payload['status'] or state['origin_job_id']!=payload['origin_job_id']
                    or identity['plan_hash']!=payload['plan_hash'] or identity['plan_revision']!=payload['plan_revision']
                    or state['teacher_review']!='NOT_RUN' or payload['teacher_review']!='NOT_RUN'):
                raise ValueError('Uncertainty event/state identity mismatch')
            for name,expected in state['dependencies'].items():
                if Path(name).name!=name:raise ValueError('Invalid dependency filename')
                data=archive(path.parent/name,path.parent,folder/name,expected);dependencies[name]=json.loads(data)
                record['dependencies'].append({'name':name,'sha256':digest(data),'archive':str(folder/name)})
            context=dependencies['input.json']
            if (digest(context)!=identity['context_hash'] or context['plan']['hash']!=identity['plan_hash']
                    or context['plan']['revision']!=identity['plan_revision']):
                raise ValueError('Uncertainty input differs from its reviewed snapshot')
            record.update(state_sha256=digest(raw),status=state['status'],context_hash=identity['context_hash'],
                section_id=context['section']['section_id'],section_hash=digest(context['section']),
                declared_doubts=context['declared_doubts'],unit_hashes={u['id']:digest(u) for u in context['section']['units']},
                matches_current_approved_plan=identity['plan_hash']==snapshot['plan']['hash'] and identity['plan_revision']==snapshot['plan']['revision'])
            if state['status']=='REVIEWED':
                from math_agent.uncertainty_review import validate_uncertainty_assessment
                replay=validate_uncertainty_assessment(dependencies[state['response_file']],context)
                if replay!=dependencies['assessment.json']:raise ValueError('Saved dispositions differ from replay')
                record.update(assessment=replay,disposition_counts=dict(Counter(i['disposition'] for i in replay['items'])),
                              saved_response_validation='PASS_NO_NEW_MODEL_CALL')
            else:record['saved_response_validation']='NOT_COMPLETE_NO_SUCCESS_CLAIM'
            record['integrity']='PASS'
        except (OSError,ValueError,KeyError,TypeError,ImportError) as error:failure(record,error)
        records.append(record)
    result={'records':records,'all_files_verified':all(r['integrity']=='PASS' for r in records),
        'meaning':'REVIEWED means dispositions recorded. resolved_by_current_body is a scoped automatic judgment, not proof or teacher approval. It does not assert the final delivery still has that body.'}
    save(output/'uncertainty-evidence.json',result)
    return result
