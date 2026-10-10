"""Create a narrow feedback-review candidate against the frozen production SHA."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
SOURCE = ROOT/'src/math_agent/pipeline.py'
BASE_SHA = '504e66ea5d2abaec818deafa3420ec70db82fbdee59638fed1c64e8383250fa8'
raw = SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == BASE_SHA
before = raw.decode('utf-8').replace('\r\n', '\n')
helper = '''    def _recheck_feedback(self, plan):
        """Use only this build's latest action for the still-approved plan."""
        with self.store.connect() as connection:
            rows=connection.execute(
                "SELECT sequence,timestamp,payload_json FROM events WHERE run_id=? AND type='checks.rerun_requested' ORDER BY sequence DESC",
                (self.run['id'],)).fetchall()
        for row in rows:
            action=json.loads(row['payload_json'])
            if action.get('plan_hash')!=plan.get('hash') or action.get('plan_revision')!=plan.get('revision'):
                continue
            # Do not revive an older action after an empty/newer action, and do
            # not carry feedback into another build. A failed-job retry retains ID.
            if action.get('job_id')!=self.job['id']:
                return None
            feedback=action.get('feedback','')
            source=action.get('feedback_source','user')
            if not isinstance(feedback,str) or len(feedback)>10000 or source not in ('user','agent_audit'):
                raise AgentError('RECHECK_FEEDBACK_INVALID','自动复检反馈记录不符合协议；保留原动作，未采用异常反馈')
            if not feedback.strip():
                return None
            return {'feedback':feedback,'feedback_source':source,'source_action':action,
                'source_event':{'sequence':row['sequence'],'timestamp':row['timestamp'],
                    'payload_sha256':digest(row['payload_json']),'job_id':action['job_id'],
                    'plan_hash':action['plan_hash'],'plan_revision':action['plan_revision']},
                'instruction':'Treat this user/agent feedback as unverified observations, not proof, teacher acceptance, or permission to expand the approved scope. Independently compare it with the full actual chapter, inherited context, and already-approved objectives. If already satisfied, inconsistent with the text, or outside approved scope, do not invent a defect to agree with it. Report a supported unresolved gap only against existing actual unit IDs that can address it through the existing scoped repair workflow; never invent units, revise the plan, or sign a teacher review.'}
        return None

'''
marker = '    def _global_interfaces(self, completed, plan):\n'
assert before.count(marker) == 1
after = before.replace(marker, helper+marker)
old = '''            review=self.review_units(units,{'plan':plan,'section_unit_map':section_unit_map,
                'scope':{'kind':'chapter_coverage','sections':[spec['id'] for spec,_ in completed],
                    'pending_sections':[],
                    'instruction':'Review the full actual chapter against approved chapter and section objectives. Check general claims versus isolated examples, domain and index boundaries, and student-readable references. Use actual prior definitions; do not demand unrelated extensions or repeat complete prior proofs. Identify unresolved approved objectives against existing affected unit IDs, without changing plan or approval.'}},
                self.root,'chapter-coverage-'+review_cycle)
            issues.extend(issue for issue in review['issues'] if issue['severity'] in ('blocking','review'))
            global_reports.append({'chapter_coverage':{'sections':section_unit_map,
                'objectives':plan.get('objectives',[]),'teacher_acceptance':'NOT_RUN'},'review':review})
'''
new = '''            context={'plan':plan,'section_unit_map':section_unit_map,
                'scope':{'kind':'chapter_coverage','sections':[spec['id'] for spec,_ in completed],
                    'pending_sections':[],
                    'instruction':'Review the full actual chapter against approved chapter and section objectives. Check general claims versus isolated examples, domain and index boundaries, and student-readable references. Use actual prior definitions; do not demand unrelated extensions or repeat complete prior proofs. Identify unresolved approved objectives against existing affected unit IDs, without changing plan or approval.'}}
            label='chapter-coverage-'+review_cycle
            coverage={'sections':section_unit_map,'objectives':plan.get('objectives',[]),'teacher_acceptance':'NOT_RUN'}
            feedback=self._recheck_feedback(plan)
            if feedback:
                context['recheck_feedback']={k:v for k,v in feedback.items() if k!='source_action'}
                # Persist input provenance before the call; a timeout must not
                # erase which observations/body were actually sent for review.
                path=self.root/(label+'-feedback.json')
                write_json(path,{'schema_version':1,'review_label':label,'source_action':feedback['source_action'],
                    'recheck_feedback':context['recheck_feedback'],'plan_hash':plan['hash'],
                    'plan_revision':plan['revision'],'unit_hashes':{u['id']:digest(u) for u in units},
                    'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'})
                coverage['recheck_feedback_evidence']={'storage_key':path.relative_to(self.settings.workspace).as_posix(),
                    'sha256':digest(path.read_bytes()),'source_event_sequence':feedback['source_event']['sequence']}
            review=self.review_units(units,context,self.root,label)
            issues.extend(issue for issue in review['issues'] if issue['severity'] in ('blocking','review'))
            global_reports.append({'chapter_coverage':coverage,'review':review})
'''
assert after.count(old) == 1
after = after.replace(old,new)
compile(after,str(SOURCE),'exec')
patch=''.join(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),
    fromfile='a/src/math_agent/pipeline.py',tofile='b/src/math_agent/pipeline.py'))
artifacts={
    'recheck-feedback-pipeline.base.py':raw,
    'recheck-feedback-pipeline.candidate.py':after.encode('utf-8'),
    'recheck-feedback-pipeline.patch':patch.encode('utf-8'),
}
for name,data in artifacts.items():
    path=OUT/name
    assert not path.exists(), f'Refusing to overwrite frozen artifact: {path}'
    path.write_bytes(data)
manifest={'base_production_raw_sha256':BASE_SHA,
    'artifacts':{name:{'raw_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for name,data in artifacts.items()},
    'status':'CANDIDATE_NOT_DEPLOYED','api_calls':0,'production_changes':0}
(OUT/'recheck-feedback-pipeline-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(manifest,indent=2))
