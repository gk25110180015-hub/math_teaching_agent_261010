"""Fenced, bounded unchecked local repair state; rejected outputs never become seeds."""
import copy
import json
from pathlib import Path

from .domain import WrittenSection
from .lecture_fragments import normalize_written_section
from .util import AgentError,digest,uid,within,write_json


BUDGET_POLICY = 'per unit accepted modifications<=configured_limit; per repair key proposal calls<=configured_limit+1 and rejected proposals<=max(2,configured_limit); stop before another proposal at a reached limit; explicit local budget increase preserves all counters, candidates and doubts; retain run request cap'


def issue_targets(issues):
    targets=set()
    for issue in issues:
        target=issue.get('unit_id') or issue.get('location',{}).get('unit_id')
        if not target:
            raise AgentError('REPAIR_SCOPE_UNCLEAR','未定位的疑点必须保留，不能借局部修复清除或扩大范围')
        targets.add(target)
    return targets


class LocalRecovery:
    def __init__(self,pipeline,spec,context,base,plan,draft,forced=False):
        self.p=pipeline;self.spec=spec;self.draft=draft
        self.path=pipeline.root/'local-repair'/(spec['id']+'.json')
        self.folder=pipeline.root/'local-repair'/spec['id']
        self.identity={'plan_hash':plan['hash'],'section_id':spec['id'],'context_hash':digest(context),
            'base_hash':digest(base),'model':getattr(pipeline,'preferred_model_name',pipeline.settings.model),'provider':pipeline.run['input']['provider']}
        self.state=None
        if not self.path.exists() and self.folder.exists() and any(self.folder.glob('candidate-*.json')):
            raise AgentError('LOCAL_REPAIR_CACHE_INVALID','局部状态指针缺失而历史候选仍存在，不能重置预算或按时间猜选稿件')
        if self.path.exists():
            try:
                old=json.loads(self.path.read_bytes())
                if old['identity']['plan_hash']==plan['hash']:
                    self.state=old;self._candidate()
                    if old['phase']=='LEGACY_IMPORT_BLOCKED':
                        raise AgentError('LOCAL_REPAIR_LEGACY_UNVERIFIED','旧局部修复链仍未验证，不能在重试时绕过原阻塞')
                    if old['identity']!=self.identity:
                        if not forced:
                            raise AgentError('LOCAL_REPAIR_IDENTITY_CHANGED','局部恢复上下文改变；旧计数和未决疑点保留，不能静默重置')
                        self.state['identity']=self.identity
                        self.save_candidate(base,'UNCHECKED_FORCED',reason='Explicit global-repair seed; existing local counters retained')
                else:
                    self._archive('previous-approved-plan',self.path)
            except (OSError,ValueError,KeyError,TypeError):
                raise AgentError('LOCAL_REPAIR_CACHE_INVALID','局部恢复状态或候选路径/哈希损坏，未替换证据') from None
        if self.state is None:
            self.state={'schema_version':1,'identity':self.identity,'phase':'UNCHECKED',
                'applied_rounds':0,'proposal_calls':0,'rejected_proposals':0,'pending_issues':[],
                'unit_applied_counts':{},'proposal_counts_by_key':{},'rejected_counts_by_key':{},'evidence_dependencies':[],
                'last_review_context_hash':None,'reference_recovery':None,'answer_recovery':None,
                'budget_policy':BUDGET_POLICY,
                'teacher_visual_review':'NOT_RUN'}
            self.save_candidate(base,'UNCHECKED')
            if not forced:self._import_legacy(base)
        write_json(draft/'local-recovery.json',{'status':'UNCHECKED_REPAIRED' if self.state['applied_rounds'] else 'UNCHECKED',
            'state_key':self.path.relative_to(self.p.settings.workspace).as_posix(),
            'candidate_key':self.state['candidate_key'],'candidate_hash':self.state['candidate_hash'],
            'applied_rounds':self.state['applied_rounds'],'proposal_calls':self.state['proposal_calls'],
            'rejected_proposals':self.state['rejected_proposals'],'pending_issues':self.state['pending_issues']})

    def _archive(self,label,path):
        target=self.folder/'history'/(label+'-'+uid()[:10]+'.json')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())

    def save(self):
        with self.p.store.transaction() as c:
            self.p.store.assert_fence(c,self.p.job)
            if self.path.exists():self._archive('state',self.path)
            write_json(self.path,self.state)
            self.p.store.event(c,self.p.run['id'],'local.repair_state',{'section_id':self.spec['id'],
                'phase':self.state['phase'],'applied_rounds':self.state['applied_rounds'],
                'proposal_calls':self.state['proposal_calls'],'rejected_proposals':self.state['rejected_proposals']})

    def _candidate(self):
        try:
            path=within(self.p.settings.workspace,self.state['candidate_key'])
            if not path.is_relative_to(self.folder.resolve()):raise ValueError('path')
            raw=path.read_bytes()
            if digest(raw)!=self.state['candidate_hash']:raise ValueError('hash')
            data=WrittenSection.model_validate(json.loads(raw)).model_dump()
            if data['section_id']!=self.spec['id']:raise ValueError('section')
            for dependency in self.state.get('evidence_dependencies',[]):
                evidence_path=within(self.p.settings.workspace,dependency['key'])
                if (not evidence_path.is_relative_to(self.p.root.resolve()) and not evidence_path.is_relative_to(self.p.build_root.resolve())) or digest(evidence_path.read_bytes())!=dependency['hash']:
                    raise AgentError(dependency.get('error_code','LOCAL_REPAIR_CACHE_INVALID'),'合法候选依赖的原提案证据SHA失配；不绕过历史证据检查')
            return data
        except (OSError,ValueError,KeyError,TypeError):
            raise AgentError('LOCAL_REPAIR_CACHE_INVALID','最近合法局部稿路径、SHA或结构失配；禁止改用被拒稿') from None

    def candidate(self):return copy.deepcopy(self._candidate())

    def save_candidate(self,section,phase,**details):
        path=self.folder/('candidate-'+uid()[:12]+'.json');write_json(path,section)
        self.state.update(candidate_key=path.relative_to(self.p.settings.workspace).as_posix(),
            candidate_hash=digest(path.read_bytes()),phase=phase,**details)
        self.save()

    def review_context(self,section,math,local_checks=None):
        from .provider import PROMPTS
        identity={'candidate_hash':digest(section),'tool_checks_hash':digest(math),
            'reviewer_prompt_hash':digest((PROMPTS/'reviewer_math.md').read_bytes()),
            'plan_context_hash':self.identity['context_hash'],
            'deterministic_checks_hash':digest(local_checks) if local_checks is not None else None}
        return identity,{'unresolved_issues':copy.deepcopy(self.state['pending_issues']),
            'prior_review_context_hash':self.state['last_review_context_hash'],
            'current_review_identity':identity,'legacy_evidence':self.state.get('legacy_import'),
            'instruction':'Explicitly reconsider the preserved issues against the actual body and locked plan. Do not erase a doubt merely because this is a retry; state unresolved issues against actual units. A changed review policy is not teacher approval.'}

    def record_review(self,issues,identity,report):
        current=[i for i in issues if i.get('severity','blocking') in ('blocking','review')]
        previous=self.state['pending_issues'];key=digest(identity)
        if previous and self.state['last_review_context_hash']==key:
            # Identical evidence must not resolve a persisted doubt by reviewer roulette.
            seen={digest(i) for i in current}
            current+=copy.deepcopy([i for i in previous if digest(i) not in seen])
        record=self.folder/('review-'+uid()[:12]+'.json')
        write_json(record,{'prior_issues':previous,'review_identity':identity,'report':report,'retained_issues':current})
        self.state.update(pending_issues=current,last_review_context_hash=key,
            last_review_key=record.relative_to(self.p.settings.workspace).as_posix(),
            phase='NEEDS_REPAIR' if current else 'LOCAL_CHECKS_PENDING_COMPILE')
        self.save();return current

    def begin_proposal(self,kind,keys,unit_ids=()):
        maximum=self.p.effective_budget()['local_repairs_per_unit']
        rejection_limit=max(2,maximum)
        self.state['budget_policy']=BUDGET_POLICY
        keys=sorted(set(keys))
        if (maximum==0 or any(self.state['unit_applied_counts'].get(i,0)>=maximum for i in unit_ids)
            or any(self.state['proposal_counts_by_key'].get(k,0)>=maximum+1 or self.state['rejected_counts_by_key'].get(k,0)>=rejection_limit for k in keys)):
            self.state['phase']='BUDGET_EXHAUSTED';self.save()
            raise AgentError('BUDGET_EXHAUSTED','kind=local_repairs_per_unit; units='+str(sorted(unit_ids))+'; used='+str(self.state['unit_applied_counts'])+'; limit='+str(maximum)+'; proposal_keys='+str(keys)+'; calls='+str(self.state['proposal_counts_by_key'])+'; rejected='+str(self.state['rejected_counts_by_key'])+'; proposal_limit='+str(maximum+1)+'; rejection_limit='+str(rejection_limit)+'。合法稿、原审批和未决问题均保留；需显式提高 local_repairs_per_unit 以容纳已用的单元修改、提案和拒稿次数，原累计次数不清零。')
        for key in keys:self.state['proposal_counts_by_key'][key]=self.state['proposal_counts_by_key'].get(key,0)+1
        self.state.update(proposal_calls=self.state['proposal_calls']+1,phase='PROPOSAL_PENDING',
            pending_operation=kind,pending_keys=keys,request_count_before=self.p.store.get_run(self.p.run['id'])['request_count'])
        self.save();return self.state['proposal_calls']

    def reject(self,error):
        for key in self.state.get('pending_keys',[]):
            self.state['rejected_counts_by_key'][key]=self.state['rejected_counts_by_key'].get(key,0)+1
        self.state.update(rejected_proposals=self.state['rejected_proposals']+1,phase='PROPOSAL_REJECTED',
            last_rejection={'code':getattr(error,'code',type(error).__name__),'message':str(error)[:1500]})
        self.save()

    def accept(self,section,**metadata):
        before=self._candidate();old_units={u['id']:u for u in before['units']}
        changed={u['id'] for u in section['units'] if old_units.get(u['id'])!=u}
        old_calcs={c.get('id'):c for c in before.get('calculations',[])}
        changed.update(c.get('unit_id') for c in section.get('calculations',[]) if old_calcs.get(c.get('id'))!=c)
        changed.discard(None)
        maximum=self.p.effective_budget()['local_repairs_per_unit']
        if any(self.state['unit_applied_counts'].get(i,0)>=maximum for i in changed):
            error=AgentError('BUDGET_EXHAUSTED','提议涉及已耗尽接受修改次数的单元；未采用新稿')
            self.reject(error);raise error
        for unit_id in changed:self.state['unit_applied_counts'][unit_id]=self.state['unit_applied_counts'].get(unit_id,0)+1
        for key,error_code in [('reference_recovery','LABEL_RECOVERY_CACHE_INVALID'),('answer_recovery','ANSWER_RECOVERY_CACHE_INVALID'),('patch_evidence','LOCAL_REPAIR_CACHE_INVALID')]:
            item=metadata.get(key) or {}
            if item.get('proposal_key'):
                path=within(self.p.settings.workspace,item['proposal_key'])
                self.state['evidence_dependencies'].append({'key':item['proposal_key'],'hash':digest(path.read_bytes()),'error_code':error_code})
        self.state.update(applied_rounds=self.state['applied_rounds']+1,**metadata)
        self.save_candidate(section,'UNCHECKED_REPAIRED')

    def checked(self):
        self.state.update(phase='CHECKED',pending_issues=[]);self.save()

    def _import_legacy(self,base):
        """Only a verified writer-cache pointer and explicit ordered hash chain."""
        from .local_patch import apply_local_patch
        reuse_path=self.draft/'draft-reuse.json'
        if not reuse_path.exists():return
        reuse=json.loads(reuse_path.read_bytes());origin=reuse.get('reused_from')
        if not origin:return
        path=within(self.p.settings.workspace,origin)
        if not path.is_relative_to(self.p.build_root.resolve()) or path.name!='candidate.json':
            raise AgentError('LOCAL_REPAIR_LEGACY_UNVERIFIED','旧稿不来自已验证writer指针')
        folder=path.parent
        if not any((folder/f'repair-{n}-raw.json').exists() for n in range(1,4)):return
        try:
            normal=json.loads((folder/'candidate-normalization.json').read_bytes())
            original=json.loads(path.read_bytes());current=json.loads((folder/'candidate-normalized.json').read_bytes())
            if normal['raw_hash']!=digest(original) or normal['normalized_hash']!=digest(current):raise ValueError('normalization hash')
            if digest(normalize_written_section(original)[0])!=digest(base):raise ValueError('writer baseline')
            dependencies=[]
            def pin(evidence_path):
                dependencies.append({'key':evidence_path.relative_to(self.p.settings.workspace).as_posix(),
                    'hash':digest(evidence_path.read_bytes()),'error_code':'LOCAL_REPAIR_LEGACY_UNVERIFIED'})
            for evidence_path in (path,folder/'candidate-normalization.json',folder/'candidate-normalized.json'):pin(evidence_path)
            records=[];last_review=None;applied=0;rejected=0;calls=0;unit_counts={};proposal_counts={};rejection_counts={}
            for number in range(1,4):
                raw_path=folder/f'repair-{number}-raw.json';applied_path=folder/f'repair-{number}.json'
                if not raw_path.exists():
                    if any((folder/f'repair-{n}-raw.json').exists() for n in range(number+1,4)):raise ValueError('repair gap')
                    break
                review_path=folder/f'review-{number-1}.json';review=json.loads(review_path.read_bytes())
                pin(raw_path);pin(review_path)
                blocking=[i for i in review['issues'] if i.get('severity','blocking') in ('blocking','review')]
                allowed=issue_targets(blocking);calls+=1;last_review=review
                for unit_id in allowed:proposal_counts['unit:'+unit_id]=proposal_counts.get('unit:'+unit_id,0)+1
                entry={'number':number,'raw_key':raw_path.relative_to(self.p.settings.workspace).as_posix(),
                    'raw_hash':digest(raw_path.read_bytes()),'review_key':review_path.relative_to(self.p.settings.workspace).as_posix(),
                    'review_hash':digest(review_path.read_bytes())}
                if not applied_path.exists():
                    rejected+=1;entry['status']='REJECTED_NOT_ADOPTED';records.append(entry)
                    for unit_id in allowed:rejection_counts['unit:'+unit_id]=rejection_counts.get('unit:'+unit_id,0)+1
                    if any((folder/f'repair-{n}-raw.json').exists() for n in range(number+1,4)):raise ValueError('uncommitted intermediate repair')
                    break
                saved=json.loads(applied_path.read_bytes());after=saved['section']
                pin(applied_path)
                if saved['before_hash']!=digest(current) or saved['after_hash']!=digest(after):raise ValueError('repair hash chain')
                normalized_raw,raw_evidence=normalize_written_section(json.loads(raw_path.read_bytes()))
                if raw_evidence['status']!='PASS' or digest(normalized_raw)!=digest(after):raise ValueError('raw proposal does not normalize to recorded applied section')
                old_units={u['id']:u for u in current['units']};new_units={u['id']:u for u in after['units']}
                old_calcs={c['id']:c for c in current.get('calculations',[])}
                changes={'section_id':self.spec['id'],'replacements':[{'unit_id':i,'tex':new_units[i]['tex']} for i in sorted(allowed)],
                    'calculation_updates':[c for c in after.get('calculations',[]) if c['id'] in old_calcs and c!=old_calcs[c['id']]],
                    'calculation_additions':[c for c in after.get('calculations',[]) if c['id'] not in old_calcs],
                    'uncertainties_append':after.get('uncertainties',[])[len(current.get('uncertainties',[])):],
                    'calculation_limitations_append':after.get('calculation_limitations',[])[len(current.get('calculation_limitations',[])):]}
                verified,_=apply_local_patch(current,allowed,changes)
                if verified!=after:raise ValueError('legacy applied repair changed unauthorized fields')
                changed={u['id'] for u in after['units'] if old_units.get(u['id'])!=u}
                changed.update(c['unit_id'] for c in after.get('calculations',[]) if old_calcs.get(c['id'])!=c)
                for unit_id in changed:unit_counts[unit_id]=unit_counts.get(unit_id,0)+1
                current=after;applied+=1;entry['status']='VERIFIED_APPLIED';entry['applied_hash']=digest(applied_path.read_bytes());records.append(entry)
                next_review=folder/f'review-{number}.json'
                if next_review.exists():last_review=json.loads(next_review.read_bytes());pin(next_review)
            if not calls:return
            maximum=self.p.effective_budget()['local_repairs_per_unit']
            if any(n>maximum for n in unit_counts.values()) or any(n>maximum+1 for n in proposal_counts.values()):raise ValueError('legacy unit budget exceeded')
            pending=[i for i in last_review['issues'] if i.get('severity','blocking') in ('blocking','review')]
            imported={'origin_candidate_key':origin,'origin_candidate_hash':digest(path.read_bytes()),'records':records,
                'total_request_count_at_import':self.p.store.get_run(self.p.run['id'])['request_count'],
                'old_reviewer_prompt_hash':'UNKNOWN_NOT_ARCHIVED','migration_policy':'Explicit patch-protocol migration: retain applied/rejected/proposal counters and all existing total requests; no budget reset.'}
            self.state.update(applied_rounds=applied,rejected_proposals=rejected,proposal_calls=calls,
                unit_applied_counts=unit_counts,proposal_counts_by_key=proposal_counts,rejected_counts_by_key=rejection_counts,
                pending_issues=pending,legacy_import=imported,last_review_context_hash=None,evidence_dependencies=dependencies)
            write_json(self.folder/('legacy-import-'+uid()[:10]+'.json'),imported)
            self.save_candidate(current,'UNCHECKED_REPAIRED')
        except (OSError,ValueError,KeyError,TypeError,AgentError) as exc:
            self.state['phase']='LEGACY_IMPORT_BLOCKED';self.save()
            raise AgentError('LOCAL_REPAIR_LEGACY_UNVERIFIED','旧局部修复无法验证完整连续哈希链；未采用任何被拒稿：'+str(exc)[:300]) from None
