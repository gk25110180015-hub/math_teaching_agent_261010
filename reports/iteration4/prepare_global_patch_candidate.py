"""Write reviewed candidate artifacts only; never modify deployed source or tests."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
files = []


def emit(source, candidate, content):
    dest = OUT / candidate
    dest.write_bytes(content.encode('utf-8'))
    base = ROOT / source
    files.append({'source': source, 'candidate': candidate,
        'baseline_sha256': hashlib.sha256(base.read_bytes()).hexdigest() if base.exists() else None,
        'candidate_sha256': hashlib.sha256(dest.read_bytes()).hexdigest()})


source = ROOT/'src/math_agent/pipeline.py'
text = source.read_text(encoding='utf-8')
start = text.index('    def _global_repair_identity(')
end = text.index('    def _save_global_repair_state(', start)
text = text[:start] + '''    def _global_repair_identity(self, plan):
        from .global_repair_contract import patch_identity
        return patch_identity(self, plan)

''' + text[end:]
text = text.replace("                if state['identity']==identity:\n                    self._global_repair_sections(state)\n                    return state",
'''                if state['identity']==identity:
                    from .global_repair_contract import resume_migration_audit
                    if type(state.get('schema_version')) is not int or state['schema_version'] != 2:
                        raise AgentError('GLOBAL_REPAIR_CACHE_INVALID','全局修复状态版本与补丁契约不一致')
                    self._global_repair_sections(state)
                    return resume_migration_audit(self,plan,state,identity)''')
text = text.replace("                if state['identity'].get('plan_hash')==plan['hash']:\n                    self._global_repair_sections(state)\n                    raise AgentError",
'''                if state['identity'].get('plan_hash')==plan['hash']:
                    self._global_repair_sections(state)
                    from .global_repair_contract import migrate_known_v1
                    migrated=migrate_known_v1(self,plan,state,identity)
                    if migrated is not None:return migrated
                    raise AgentError''')
text = text.replace("return {'schema_version':1,'identity':identity,'rounds_used':0,'phase':'not_started',",
                    "return {'schema_version':2,'identity':identity,'rounds_used':0,'phase':'not_started',")
start = text.index('    def _continue_global_repairs(')
end = text.index('    def lecture(', start)
method = '''    def _continue_global_repairs(self, plan, state):
        from .calculation_protocol import calculation_protocol
        from .lecture_fragments import normalize_written_section
        from .local_patch import LocalPatch,apply_local_patch
        folder=within(self.settings.workspace,state['round_directory'])
        while state['pending']:
            if state['rounds_used']>self.effective_budget()['global_repair_rounds']:
                raise AgentError('BUDGET_EXHAUSTED','当前全局修复轮次超出有效额度；原疑点和候选保留')
            request=state['pending'][0]
            sid=request['section_id'];allowed=set(request['allowed_unit_ids'])
            before=self._global_repair_sections(state)[sid]
            prefix=sid+'-'+uid()[:8]
            write_json(folder/(prefix+'-before.json'),before)
            self.stage('REPAIRING','repair.global.'+sid)
            raw=self.provider.generate('repair_local_patch',{'section':before,'issues':request['issues'],
                'allowed_unit_ids':sorted(allowed),'plan':plan,'calculation_protocol':calculation_protocol(),
                'scope':'global_interface_repair','adjacent_sections':request['neighbors'],
                'metadata_policy':'Only authorized tex replacements and calculation updates/additions; preserve every other field.'},LocalPatch)
            write_json(folder/(prefix+'-raw.json'),raw)
            try:
                repaired,patch_evidence=apply_local_patch(before,allowed,raw)
            except ValueError as error:
                write_json(folder/(prefix+'-rejected.json'),{'status':'REJECTED','code':'GLOBAL_REPAIR_SCOPE_VIOLATION',
                    'message':str(error)[:2000],'source_hash':digest(before),'proposal_hash':digest(raw),
                    'allowed_unit_ids':sorted(allowed),'teacher_review':'NOT_RUN'})
                raise AgentError('GLOBAL_REPAIR_SCOPE_VIOLATION','全局局部补丁越界或结构不合法；原稿和提案保留：'+str(error)[:500]) from None
            selected={**repaired,'units':[copy.deepcopy(u) for u in repaired['units'] if u['id'] in allowed]}
            normalized,normalization=normalize_written_section(selected)
            normalized_by_id={u['id']:u['tex'] for u in normalized['units']}
            for unit in repaired['units']:
                if unit['id'] in normalized_by_id:unit['tex']=normalized_by_id[unit['id']]
            write_json(folder/(prefix+'-patch-evidence.json'),patch_evidence)
            write_json(folder/(prefix+'-normalization.json'),normalization)
            write_json(folder/(prefix+'-normalized.json'),repaired)
            before_ids=[u['id'] for u in before['units']]
            after_ids=[u['id'] for u in repaired['units']]
            by_id={u['id']:u for u in repaired['units']}
            if (repaired['section_id']!=sid or before_ids!=after_ids
                or not allowed.issubset(before_ids)
                or any(u!=by_id.get(u['id']) for u in before['units'] if u['id'] not in allowed)
                or any({k:v for k,v in u.items() if k!='tex'}!={k:v for k,v in by_id[u['id']].items() if k!='tex'}
                       for u in before['units'])):
                raise AgentError('GLOBAL_REPAIR_SCOPE_VIOLATION','全局补丁改变了单元身份、元数据或未授权正文；未采用')
            old_calcs=[c for c in before.get('calculations',[]) if c.get('unit_id') not in allowed]
            new_calcs=[c for c in repaired.get('calculations',[]) if c.get('unit_id') not in allowed]
            if old_calcs!=new_calcs or any(repaired.get(key,[])[:len(before.get(key,[]))]!=before.get(key,[])
                    for key in ('uncertainties','calculation_limitations')):
                raise AgentError('GLOBAL_REPAIR_SCOPE_VIOLATION','全局补丁改变了非目标核算或删除旧疑点；未采用')
            if normalization['status']!='PASS':
                raise AgentError('GLOBAL_REPAIR_NORMALIZATION_BLOCKED','全局修复片段存在不明确结构，不能自动采用')
            path=folder/(prefix+'-candidate.json')
            write_json(path,repaired)
            # Fence after a late provider response before accepting its result.
            with self.store.transaction() as connection:
                self.store.assert_fence(connection,self.job)
            next_state=copy.deepcopy(state)
            next_state['sections'][sid]={'candidate_key':path.relative_to(self.settings.workspace).as_posix(),
                'candidate_hash':digest(path.read_bytes())}
            next_state['pending'].pop(0)
            self._save_global_repair_state(next_state)
            state.clear();state.update(next_state)
        state['phase']='checking'
        self._save_global_repair_state(state)

'''
text = text[:start] + method + text[end:]
text = text.replace("'review_evidence_attribution.py')", "'review_evidence_attribution.py','global_repair_contract.py')")
emit('src/math_agent/pipeline.py','global-patch-pipeline.candidate.py',text)
helper = OUT/'global_repair_contract.candidate.py'
files.append({'source':'src/math_agent/global_repair_contract.py','candidate':helper.name,
              'baseline_sha256':None,'candidate_sha256':hashlib.sha256(helper.read_bytes()).hexdigest()})

global_test = (ROOT/'tests/test_global_repair.py').read_text(encoding='utf-8')
global_test = global_test.replace("if role=='repair_content_unit':", "if role=='repair_local_patch':")
old = """            if self.mode=='mutate_uncertainties':result['uncertainties']=['Unrelated metadata changed']
            return result"""
new = """            if self.mode=='mutate_uncertainties':result['uncertainties']=['Unrelated metadata changed']
            # Deliberately invalid full-section responses remain rejected, never sanitized.
            if self.mode in ('mutate_other','add_unit','drop_other_calculation','mutate_uncertainties'):
                return result
            return {'section_id':result['section_id'],'replacements':[
                {'unit_id':unit['id'],'tex':unit['tex']} for unit in result['units']
                if unit['id'] in context['allowed_unit_ids']]}"""
assert old in global_test
global_test = global_test.replace(old,new)
emit('tests/test_global_repair.py','global-patch-test_global_repair.candidate.py',global_test)

for name in ('test_global_budget_resume.py','test_teaching_quality_gate.py','test_recheck_feedback_history.py'):
    value=(ROOT/'tests'/name).read_text(encoding='utf-8').replace('repair_content_unit','repair_local_patch')
    if name=='test_teaching_quality_gate.py':
        old="""            self.problem = False
            return result"""
        new="""            self.problem = False
            return {'section_id':result['section_id'],'replacements':[
                {'unit_id':unit['id'],'tex':unit['tex']} for unit in result['units']
                if unit['id'] in context['allowed_unit_ids']]}"""
        assert old in value;value=value.replace(old,new)
    if name=='test_recheck_feedback_history.py':
        old="""            target['tex']+=marker
            return result"""
        new="""            target['tex']+=marker
            return {'section_id':result['section_id'],'replacements':[
                {'unit_id':unit['id'],'tex':unit['tex']} for unit in result['units']
                if unit['id'] in context['allowed_unit_ids']]}"""
        assert old in value;value=value.replace(old,new)
    emit('tests/'+name,'global-patch-'+name.replace('.py','.candidate.py'),value)

test=OUT/'test_global_strict_patch_migration.candidate.py'
if test.exists():
    files.append({'source':'tests/test_global_strict_patch_migration.py','candidate':test.name,
                  'baseline_sha256':None,'candidate_sha256':hashlib.sha256(test.read_bytes()).hexdigest()})
fixture_source=json.loads((OUT/'CH02-global-r3-rejected-proposal-evidence.json').read_text(encoding='utf-8'))['files']
fixture={'source_report':'reports/iteration4/CH02-global-r3-rejected-proposal-evidence.json',
    'before':fixture_source['S02-ec86609b-before.json']['value'],
    'rejected':fixture_source['S02-ec86609b-normalized.json']['value'],
    'original_before_sha256':fixture_source['S02-ec86609b-before.json']['sha256'],
    'original_rejected_sha256':fixture_source['S02-ec86609b-normalized.json']['sha256'],
    'allowed_unit_ids':['S02.U14']}
emit('tests/fixtures/global_patch_ch02_rejected.json','global-patch-ch02-rejected.fixture.json',
     json.dumps(fixture,ensure_ascii=False,indent=2))
manifest={'status':'CANDIDATE_PENDING_TESTS_AND_REVIEW','files':files,'real_api':'NOT_RUN',
          'windows_compile':'NOT_RUN','teacher_review':'NOT_RUN'}
(OUT/'global-strict-patch-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
patch=''
for item in files:
    original=(ROOT/item['source']).read_text(encoding='utf-8').splitlines(keepends=True) if (ROOT/item['source']).exists() else []
    proposed=(OUT/item['candidate']).read_text(encoding='utf-8').splitlines(keepends=True)
    patch+=''.join(difflib.unified_diff(original,proposed,fromfile='a/'+item['source'],tofile='b/'+item['source']))
(OUT/'global-strict-patch.patch').write_text(patch,encoding='utf-8')
print(json.dumps({'status':manifest['status'],'files':len(files)},ensure_ascii=False))
