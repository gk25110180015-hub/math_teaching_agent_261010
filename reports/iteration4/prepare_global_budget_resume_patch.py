"""Generate a narrow global-budget recovery proposal; production remains untouched."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
source = ROOT / 'src/math_agent/pipeline.py'
original = source.read_text(encoding='utf-8')
candidate = original


def replace(before, after):
    global candidate
    assert candidate.count(before) == 1, (before, candidate.count(before))
    candidate = candidate.replace(before, after, 1)


replace('    def _import_legacy_global_failure(self, plan, state):',
        '    def _import_legacy_global_failure(self, plan, state, *, resume_exhausted=False):')
replace("        if state['phase']!='not_started' or not failure.is_file():\n            return\n",
        "        expected_phase='budget_exhausted' if resume_exhausted else 'not_started'\n        if state['phase']!=expected_phase or not failure.is_file():\n            if resume_exhausted:\n                raise AgentError('GLOBAL_REPAIR_LEGACY_UNVERIFIED','增额恢复所需的原全局疑点记录缺失；不重置修复状态')\n            return\n")
replace("            if not issues:\n                return\n            if record.get('plan_hash',plan['hash'])!=plan['hash']:",
        "            if not issues:\n                if resume_exhausted:raise ValueError('Exhausted repair lost its unresolved concerns')\n                return\n            if resume_exhausted and record.get('rounds_used',0)!=state['rounds_used']:\n                raise ValueError('Recorded failure belongs to a different repair round')\n            if record.get('plan_hash',plan['hash'])!=plan['hash']:")
replace("            if any(k not in units or digest(units[k])!=v for k,v in record.get('unit_hashes',{}).items()):",
        "            if resume_exhausted and state['rounds_used'] and set(record.get('unit_hashes',{}))!=set(units):\n                raise ValueError('Exhausted failure does not identify the complete checked body')\n            if any(k not in units or digest(units[k])!=v for k,v in record.get('unit_hashes',{}).items()):")
replace("        write_json(self.root/'global-repairs'/'legacy-failure-import.json',{",
        "        import_evidence=self.root/'global-repairs'/('budget-resume-'+uid()[:12]+'.json' if resume_exhausted else 'legacy-failure-import.json')\n        write_json(import_evidence,{")
replace("        self._start_global_repair(canonical_completed,issues,state)\n",
        "        rounds_before=state['rounds_used']\n        requests_before=self.store.get_run(self.run['id'])['request_count']\n        self._start_global_repair(canonical_completed,issues,state)\n        if resume_exhausted:\n            budget=self.effective_budget()\n            with self.store.transaction() as connection:\n                self.store.assert_fence(connection,self.job)\n                self.store.event(connection,self.run['id'],'global.budget_resumed',{\n                    'rounds_used_before':rounds_before,'rounds_used_after':state['rounds_used'],\n                    'effective_global_limit':budget['global_repair_rounds'],'budget_version':budget['version'],\n                    'request_count_preserved':requests_before,'approval_preserved':True,\n                    'failure_source_hash':digest(raw),'evidence_key':import_evidence.relative_to(self.settings.workspace).as_posix(),\n                    'pending_issues':issues,'teacher_review':'NOT_PERFORMED'})\n")
replace("        if state['phase']=='budget_exhausted':\n            raise AgentError('GLOBAL_MATH_BLOCKED','全局修复预算已耗尽；已保留实际疑点、所有修复与原审批')\n        self._import_legacy_global_failure(plan,state)",
        "        if state['phase']=='budget_exhausted':\n            limit=self.effective_budget()['global_repair_rounds']\n            if state['rounds_used']>=limit:\n                raise AgentError('BUDGET_EXHAUSTED','kind=global_repair_rounds; used='+str(state['rounds_used'])+'; limit='+str(limit)+'。需显式提高全局修复额度；原轮次、请求计数、疑点和审批均保留。')\n            self._import_legacy_global_failure(plan,state,resume_exhausted=True)\n        else:\n            self._import_legacy_global_failure(plan,state)")
compile(candidate,str(source)+'.proposed','exec')
target = OUT / 'global-budget-resume.candidate.py'
target.write_text(candidate, encoding='utf-8', newline='\n')
patch = ''.join(difflib.unified_diff(original.splitlines(keepends=True),candidate.splitlines(keepends=True),
                                  fromfile='a/src/math_agent/pipeline.py',tofile='b/src/math_agent/pipeline.py'))
(OUT / 'global-budget-resume.patch').write_text(patch,encoding='utf-8',newline='\n')
manifest={'status':'PROPOSED_NOT_APPLIED','baseline_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'candidate_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
          'red_regression':{'passed':0,'failed':6},'real_api':'NOT_RUN','windows_compile':'NOT_RUN','teacher_review':'NOT_RUN'}
(OUT / 'global-budget-resume-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
assert source.read_text(encoding='utf-8')==original
print(json.dumps(manifest))
