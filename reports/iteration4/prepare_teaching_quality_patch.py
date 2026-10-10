"""Layer a review candidate on the preserved cache candidate; production is read only."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
source = ROOT / 'src/math_agent/pipeline.py'
before = source.read_text(encoding='utf-8')
after = (OUT / 'cached-review-refresh.candidate.py').read_text(encoding='utf-8')
start=after.index('    def _verified_section_checkpoints(self, plan):\n')
end=after.index('    def _section_recheck_seed(self, spec, saved, plan):\n',start)
after=after[:start]+'''    def _verified_section_checkpoints(self, plan):
        """Select the latest verified approved version, preserving legacy prefix proof."""
        snapshots={};prefix=[];proof_rows=[];intact_prefix=True;has_legacy=False;rows={}
        with self.store.connect() as connection:
            for row in connection.execute('SELECT rowid AS checkpoint_rowid,* FROM steps WHERE run_id=? '
                    'ORDER BY created_at DESC,rowid DESC',(self.run['id'],)).fetchall():
                rows.setdefault(row['step_key'],[]).append(dict(row))
        for spec in plan['sections']:
            selected=None
            expected_identity=self._section_check_identity(plan,spec)
            expected_input=self._section_input_hash(plan,spec,prefix)
            for row in rows.get('section.'+spec['id'],[]):
                try:
                    declared_output=json.loads(row['output_json'])
                    if not isinstance(declared_output,dict) or digest(declared_output)!=row['output_hash']:
                        raise ValueError('Checkpoint SHA mismatch')
                    declared=declared_output.get('check_identity')
                except (ValueError,TypeError):
                    raise AgentError('SECTION_CHECKPOINT_INVALID','最近章节checkpoint输出损坏，不能回退更早PASS绕过') from None
                matches_prefix=row['input_hash']==expected_input
                if declared is not None:
                    if declared!=expected_identity:continue
                elif not matches_prefix and not self._legacy_checkpoint_proven(row,plan):
                    continue
                # This is the latest eligible row. A bad source must block;
                # never continue to an older version after verification fails.
                saved=self._validate_section_checkpoint(row,spec,plan)
                selected=(row,saved,matches_prefix,declared)
                break
            if selected is None:break
            row,saved,matches_prefix,declared=selected
            snapshots[spec['id']]={'input_hash':row['input_hash'],'output':saved}
            intact_prefix=intact_prefix and matches_prefix
            if intact_prefix:
                proof_rows.append(row)
                has_legacy=has_legacy or declared is None
            prefix.append((spec,saved['generated']))
        if proof_rows and has_legacy:
            proof={'schema_version':1,'plan_hash':plan['hash'],'rows':proof_rows}
            path=self.root/'section-checkpoint-snapshots'/(digest(proof)+'.json')
            if not path.exists():
                with self.store.transaction() as connection:
                    self.store.assert_fence(connection,self.job)
                    write_json(path,proof)
                    self.store.event(connection,self.run['id'],'section.checkpoint_prefix_preserved',
                        {'proof_key':path.relative_to(self.settings.workspace).as_posix(),
                         'proof_hash':digest(proof),'section_ids':[row['step_key'] for row in proof_rows]})
        return snapshots

'''+after[end:]
helper = r'''def visible_internal_unit_ids(tex):
    """Find unambiguous workflow IDs in displayed prose, without rewriting TeX."""
    from .parsing import uncomment, _mask_verbatim, _inactive_regions, _masked_intervals, _group
    clean=uncomment(_mask_verbatim(tex))
    clean=_masked_intervals(clean,_inactive_regions(clean))
    hidden=[]
    for token in re.finditer(r'\\(?:label|ref|eqref|pageref|autoref|nameref|cref|Cref|vref|href|hyperlink|hypertarget)\*?(?![A-Za-z@])',clean):
        try:
            _,end=_group(clean,token.end())
            hidden.append((token.end(),end))
        except ValueError:
            pass  # Malformed commands remain visible and are checked separately.
    for token in re.finditer(r'\\hyperref\*?(?![A-Za-z@])\s*\[',clean):
        try:
            _,end=_group(clean,token.end()-1,'[',']')
            hidden.append((token.end()-1,end))
        except ValueError:
            pass
    clean=_masked_intervals(clean,hidden)
    return sorted(set(re.findall(r'(?<![A-Za-z0-9_])S[0-9]{2,}[.-]U[0-9]{2,}(?![A-Za-z0-9_])',clean)))


'''
needle='class Pipeline:\n'
assert after.count(needle)==1;after=after.replace(needle,helper+needle)
old="""        for u in units:
            if re.search(r'\\\\(?:documentclass|usepackage|RequirePackage|newcommand|renewcommand|def|gdef|global|section|subsection|input|include)(?![A-Za-z@])|\\\\(?:begin|end)\\{document\\}',u['tex']):"""
new="""        for u in units:
            leaked_ids=visible_internal_unit_ids(u['tex'])
            if leaked_ids:
                issues.append({'rule_id':'INTERNAL_UNIT_ID_VISIBLE','severity':'blocking','unit_id':u['id'],
                    'message':'学生正文出现内部单元ID '+', '.join(leaked_ids)+'；保留数学内容，改为自然名称或已存在且语义正确的编号引用，不得编造标签。',
                    'evidence':leaked_ids})
            if re.search(r'\\\\(?:documentclass|usepackage|RequirePackage|newcommand|renewcommand|def|gdef|global|section|subsection|input|include)(?![A-Za-z@])|\\\\(?:begin|end)\\{document\\}',u['tex']):"""
assert after.count(old)==1;after=after.replace(old,new)
old="""        if not state_path.exists():return copy.deepcopy(saved['generated'])"""
new="""        if not state_path.exists():return copy.deepcopy(saved['generated']) if saved is not None else None"""
assert after.count(old)==1;after=after.replace(old,new)
needle='    def _lecture_sections(self, plan, forced_sections=None, on_rechecked=None):\n'
helper='''    def _unchecked_section_recheck_seed(self, spec, context, plan):
        """Always retain valid accepted uncheckpointed repairs, including repeated retries."""
        path=self.root/'local-repair'/(spec['id']+'.json')
        if not path.exists():
            folder=self.root/'local-repair'/spec['id']
            if folder.exists() and any(folder.glob('candidate-*.json')):
                raise AgentError('LOCAL_REPAIR_CACHE_INVALID','局部状态指针缺失而历史候选存在，不能先重调writer或重置预算')
            return None
        try:
            state=json.loads(path.read_bytes());identity=state['identity']
            if identity['plan_hash']!=plan['hash']:return None
            approved=next((section for section in plan['sections'] if section['id']==spec['id']),None)
            if approved!=spec:raise ValueError('Current section differs from approved specification')
        except (OSError,ValueError,KeyError,TypeError):
            raise AgentError('LOCAL_REPAIR_CACHE_INVALID','未检查稿的审批/上下文身份不可核实；保留稿件与计数') from None
        return self._section_recheck_seed(spec,None,plan)

'''
assert after.count(needle)==1;after=after.replace(needle,helper+needle)
old="""            if sid in forced_sections:
                generated=copy.deepcopy(forced_sections[sid])"""
new="""            unchecked_seed=(self._unchecked_section_recheck_seed(spec,context,plan)
                if sid not in forced_sections and not cached else None)
            if sid in forced_sections:
                generated=copy.deepcopy(forced_sections[sid])"""
assert after.count(old)==1;after=after.replace(old,new)
old="""            else:
                generated,draft = self.writer_draft(spec,context)
            generated, normalization = normalize_written_section(generated)"""
new="""            elif unchecked_seed is not None:
                generated=unchecked_seed
                draft=self.build_root/('s'+sid+'_'+uid()[:12])
                draft.mkdir(parents=True,exist_ok=False)
                write_json(draft/'candidate.json',generated)
                write_json(draft/'unchecked-local-recheck.json',{'section_id':sid,'status':'UNCHECKED',
                    'candidate_hash':digest(generated),
                    'state_key':(self.root/'local-repair'/(sid+'.json')).relative_to(self.settings.workspace).as_posix(),
                    'reason':'Approved accepted local candidate without a checkpoint; recheck changed prior context without reauthoring or resetting counters'})
            else:
                generated,draft = self.writer_draft(spec,context)
            generated, normalization = normalize_written_section(generated)"""
assert after.count(old)==1;after=after.replace(old,new)
old='recovery=LocalRecovery(self,spec,context,generated,plan,draft,forced=sid in forced_sections or bool(cached))'
new='recovery=LocalRecovery(self,spec,context,generated,plan,draft,forced=sid in forced_sections or bool(cached) or unchecked_seed is not None)'
assert after.count(old)==1;after=after.replace(old,new)
old="""        review_cycle=uid()[:8]
        # Check actual complete bodies plus each adjacent dependency interface.
"""
new="""        review_cycle=uid()[:8]
        if [spec['id'] for spec,_ in completed]!=[spec['id'] for spec in plan['sections']]:
            raise AgentError('INCOMPLETE_CHAPTER_REVIEW','全章语义检查需要全部批准章节的实际正文，不能以部分稿认定目标覆盖')
        # Check actual complete bodies plus each adjacent dependency interface.
"""
assert after.count(old)==1;after=after.replace(old,new)
old="""            review=self.review_units(units,{'plan':plan,'scope':{'kind':'adjacent_interface','sections':[completed[i][0]['id'],completed[i+1][0]['id']],"""
new="""            review=self.review_units(units,{'plan':plan,'prior_sections':[g for _,g in completed[:i]],
                'scope':{'kind':'adjacent_interface','sections':[completed[i][0]['id'],completed[i+1][0]['id']],"""
assert after.count(old)==1;after=after.replace(old,new)
old="""            global_reports.append({'global_interface':[completed[i][0]['id'],completed[i+1][0]['id']],'review':review})
        return global_reports,issues
"""
new="""            global_reports.append({'global_interface':[completed[i][0]['id'],completed[i+1][0]['id']],'review':review})
        if not issues and completed:
            self.stage('GLOBAL_REVIEW','teaching.chapter_coverage')
            section_unit_map=[{'section_id':spec['id'],'title':spec['title'],
                'objectives':spec.get('objectives',[]),'unit_ids':[u['id'] for u in generated['units']]}
                for spec,generated in completed]
            units=[u for _,generated in completed for u in generated['units']]
            review=self.review_units(units,{'plan':plan,'section_unit_map':section_unit_map,
                'scope':{'kind':'chapter_coverage','sections':[spec['id'] for spec,_ in completed],
                    'pending_sections':[],
                    'instruction':'Review the full actual chapter against approved chapter and section objectives. Check general claims versus isolated examples, domain and index boundaries, and student-readable references. Use actual prior definitions; do not demand unrelated extensions or repeat complete prior proofs. Identify unresolved approved objectives against existing affected unit IDs, without changing plan or approval.'}},
                self.root,'chapter-coverage-'+review_cycle)
            issues.extend(issue for issue in review['issues'] if issue['severity'] in ('blocking','review'))
            global_reports.append({'chapter_coverage':{'sections':section_unit_map,
                'objectives':plan.get('objectives',[]),'teacher_acceptance':'NOT_RUN'},'review':review})
        return global_reports,issues
"""
assert after.count(old)==1;after=after.replace(old,new)
prompt_path = ROOT / 'src/math_agent/prompts/reviewer_math.md'
prompt_before = prompt_path.read_text(encoding='utf-8')
prompt_after = prompt_before.replace('版本 4。', '版本 5。', 1).rstrip()+'\n\n'+(OUT/'teaching-review-addendum.txt').read_text(encoding='utf-8')
patch=''.join(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),
    fromfile='a/src/math_agent/pipeline.py',tofile='b/src/math_agent/pipeline.py'))
patch+=''.join(difflib.unified_diff(prompt_before.splitlines(keepends=True),prompt_after.splitlines(keepends=True),
    fromfile='a/src/math_agent/prompts/reviewer_math.md',tofile='b/src/math_agent/prompts/reviewer_math.md'))
for name in ('cached-teaching-quality-combined.patch','cached-teaching-quality-combined.candidate.py','reviewer_math_v5.candidate.md'):
    existing=OUT/name
    if existing.is_file():
        history=OUT/'teaching-candidate-history'
        history.mkdir(exist_ok=True)
        shutil.copyfile(existing,history/(existing.stem+'-'+hashlib.sha256(existing.read_bytes()).hexdigest()[:12]+existing.suffix))
(OUT/'cached-teaching-quality-combined.patch').write_text(patch,encoding='utf-8')
(OUT/'cached-teaching-quality-combined.candidate.py').write_text(after,encoding='utf-8')
(OUT/'reviewer_math_v5.candidate.md').write_text(prompt_after,encoding='utf-8')
(OUT/'cached-teaching-quality-base.json').write_text(json.dumps({str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (source,prompt_path)},indent=2),encoding='utf-8')
print('Combined pipeline and reviewer v5 patch prepared; production source/prompts unchanged.')
