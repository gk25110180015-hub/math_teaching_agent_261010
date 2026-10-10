"""Prepare an isolated proposed patch; never modify production source."""
from pathlib import Path
import difflib
import hashlib

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'src/math_agent/pipeline.py'
before = source.read_text(encoding='utf-8')
helpers = '''    def _section_check_contract(self):
        """Pin the checks that justify reuse; writer authorship is not a check."""
        from .provider import PROMPTS
        modules=('pipeline.py','mathcheck.py','lecture_fragments.py','crossrefs.py',
                 'parsing.py','compiler.py','calculation_protocol.py','local_recovery.py')
        domain_checker=Path(__file__).with_name('series_domain_text.py')
        return {'schema_version':1,
            'source_hashes':{**{name:digest(Path(__file__).with_name(name).read_bytes()) for name in modules},
                'series_domain_text.py':digest(domain_checker.read_bytes()) if domain_checker.is_file() else 'MISSING'},
            'reviewer_prompt_hash':digest((PROMPTS/'reviewer_math.md').read_bytes()),
            'review_schema_hash':digest(MathReview.model_json_schema()),
            'written_schema_hash':digest(WrittenSection.model_json_schema()),
            'checker_dependencies':{name:importlib.metadata.version(name) for name in ('sympy','pylatexenc')},
            'compile_mode':self.settings.compile_mode,'xelatex_path':self.settings.xelatex_path}

    def _section_input_hash(self, plan, spec, completed):
        # Keep the original key formula so legacy checkpoints can be verified
        # against their original complete prefix before any recheck changes it.
        return digest([plan['hash'],spec,[digest(g) for _,g in completed],
            'writer-v4-labeled-eq-global-repair',self.preferred_model_name,self.settings.xelatex_path,'rules-v1'])

    def _section_check_identity(self, plan, spec):
        return {'plan_hash':plan['hash'],'section_hash':digest(spec),
                'model':self.preferred_model_name,'provider':self.run['input']['provider']}

    def _validate_section_checkpoint(self, row, spec, plan):
        try:
            saved=json.loads(row['output_json'])
            if digest(saved)!=row['output_hash']:raise ValueError('Checkpoint SHA mismatch')
            identity=saved.get('check_identity')
            if identity is not None and identity!=self._section_check_identity(plan,spec):
                raise ValueError('Checkpoint plan/spec identity mismatch')
            path=within(self.settings.workspace,saved['source_key'])
            if not path.is_relative_to(self.build_root.resolve()) or not path.is_file():
                raise ValueError('Checkpoint source is outside controlled build directory')
            if digest(path.read_bytes())!=saved['source_hash']:raise ValueError('Source SHA mismatch')
            generated=WrittenSection.model_validate(saved['generated']).model_dump()
            if generated['section_id']!=spec['id']:raise ValueError('Checkpoint section ID mismatch')
            return saved
        except (OSError,ValueError,KeyError,TypeError):
            raise AgentError('SECTION_CHECKPOINT_INVALID',
                '已检查章节的正文/源文件/审批身份或SHA不一致；保留证据，不能改用新writer绕过') from None

    def _legacy_checkpoint_proven(self, target, plan):
        """Recompute historical prefix keys, never trust a recorded plan label alone."""
        for path in (self.root/'section-checkpoint-snapshots').glob('*.json'):
            try:
                proof=json.loads(path.read_bytes())
                if digest(proof)!=path.stem:raise ValueError('Prefix proof SHA mismatch')
                if proof['plan_hash']!=plan['hash']:continue
                prefix=[]
                for spec,row in zip(plan['sections'],proof['rows']):
                    if row['step_key']!='section.'+spec['id']:raise ValueError('Prefix order mismatch')
                    if row['input_hash']!=self._section_input_hash(plan,spec,prefix):
                        raise ValueError('Historical prefix identity mismatch')
                    saved=self._validate_section_checkpoint(row,spec,plan)
                    if row['step_key']==target['step_key']:
                        if (row['input_hash'],row['output_hash'])==(target['input_hash'],target['output_hash']):
                            return True
                        break
                    prefix.append((spec,saved['generated']))
            except (OSError,ValueError,KeyError,TypeError):
                raise AgentError('SECTION_CHECKPOINT_INVALID',
                    '旧章节的持久前缀证明损坏，不能忽略身份哈希后继续') from None
        return False

    def _verified_section_checkpoints(self, plan):
        """Verify and preserve the old prefix before upstream rechecks can change it."""
        snapshots={};prefix=[];proof_rows=[];intact_prefix=True;has_legacy=False
        with self.store.connect() as connection:
            rows={row['step_key']:dict(row) for row in connection.execute(
                'SELECT * FROM steps WHERE run_id=?',(self.run['id'],)).fetchall()}
        for spec in plan['sections']:
            row=rows.get('section.'+spec['id'])
            if row is None:break
            try:
                declared=json.loads(row['output_json']).get('check_identity')
            except (ValueError,TypeError):
                raise AgentError('SECTION_CHECKPOINT_INVALID','章节checkpoint不可解析；保留证据') from None
            matches_prefix=row['input_hash']==self._section_input_hash(plan,spec,prefix)
            if declared is not None:
                if declared!=self._section_check_identity(plan,spec):break
            elif not matches_prefix and not self._legacy_checkpoint_proven(row,plan):
                break  # No evidence that this legacy body belongs to the approved plan.
            saved=self._validate_section_checkpoint(row,spec,plan)
            snapshots[spec['id']]={'input_hash':row['input_hash'],'output':saved}
            intact_prefix=intact_prefix and matches_prefix
            if intact_prefix:
                proof_rows.append(row)
                has_legacy=has_legacy or declared is None
            # Keys used the exact stored object, not a migrated schema dump.
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

    def _section_recheck_seed(self, spec, saved, plan):
        """Prefer any later accepted local repair; never roll back to old PASS."""
        state_path=self.root/'local-repair'/(spec['id']+'.json')
        if not state_path.exists():return copy.deepcopy(saved['generated'])
        try:
            state=json.loads(state_path.read_bytes());identity=state['identity']
            expected={'plan_hash':plan['hash'],'section_id':spec['id'],
                'model':self.preferred_model_name,'provider':self.run['input']['provider']}
            if any(identity.get(key)!=value for key,value in expected.items()):
                raise ValueError('Local repair belongs to different approved content')
            path=within(self.settings.workspace,state['candidate_key'])
            if not path.is_relative_to((self.root/'local-repair'/spec['id']).resolve()):
                raise ValueError('Local repair candidate path mismatch')
            raw=path.read_bytes()
            if digest(raw)!=state['candidate_hash']:raise ValueError('Local repair candidate SHA mismatch')
            generated=WrittenSection.model_validate(json.loads(raw)).model_dump()
            if generated['section_id']!=spec['id']:raise ValueError('Local repair section ID mismatch')
            # LocalRecovery verifies every evidence dependency before adopting
            # this seed and retains counters/pending issues under forced rebasing.
            return generated
        except (OSError,ValueError,KeyError,TypeError):
            raise AgentError('LOCAL_REPAIR_CACHE_INVALID',
                '重检所需的最近合法局部稿身份、路径或SHA不一致；不能回退旧PASS或重置计数') from None

'''
needle='    def _lecture_sections(self, plan, forced_sections=None, on_rechecked=None):\n'
assert before.count(needle)==1
after=before.replace(needle,helpers+needle)
old='''        forced_sections=forced_sections or {}
        for spec in plan['sections']:
'''
new='''        forced_sections=forced_sections or {}
        check_contract=self._section_check_contract()
        checkpoints=self._verified_section_checkpoints(plan)
        for spec in plan['sections']:
'''
assert after.count(old)==1;after=after.replace(old,new)
old='''            cache_key = digest([plan['hash'], spec, [digest(g) for _,g in completed], 'writer-v4-labeled-eq-global-repair', self.preferred_model_name, self.settings.xelatex_path, 'rules-v1'])
            cached = self.store.cached_step(self.run['id'], 'section.'+sid, cache_key)
            if cached and sid not in forced_sections:
                p = within(self.settings.workspace, cached['source_key'])
                if p.is_file() and digest(p.read_bytes()) == cached['source_hash']:
                    completed.append((spec,cached['generated']))
                    local_reports.append(cached['report'])
                    continue
'''
new='''            cache_key=self._section_input_hash(plan,spec,completed)
            snapshot=checkpoints.get(sid)
            cached=snapshot['output'] if snapshot else None
            if (cached and sid not in forced_sections and snapshot['input_hash']==cache_key
                    and cached.get('check_contract')==check_contract):
                completed.append((spec,cached['generated']))
                local_reports.append(cached['report'])
                continue
'''
assert after.count(old)==1;after=after.replace(old,new)
old='''            else:
                generated,draft = self.writer_draft(spec,context)
            generated, normalization = normalize_written_section(generated)
'''
new='''            elif cached:
                generated=self._section_recheck_seed(spec,cached,plan)
                draft=self.build_root/('s'+sid+'_'+uid()[:12])
                draft.mkdir(parents=True,exist_ok=False)
                write_json(draft/'candidate.json',generated)
                write_json(draft/'checkpoint-recheck.json',{'section_id':sid,'status':'UNCHECKED',
                    'candidate_hash':digest(generated),'checkpoint_generated_hash':digest(cached['generated']),
                    'source_key':cached['source_key'],'source_hash':cached['source_hash'],
                    'previous_contract':cached.get('check_contract'),'current_contract':check_contract,
                    'dependency_changed':snapshot['input_hash']!=cache_key,
                    'reason':'Recheck preserved accepted body after check-contract/dependency changes; retain approval and repair counters'})
            else:
                generated,draft = self.writer_draft(spec,context)
            generated, normalization = normalize_written_section(generated)
'''
assert after.count(old)==1;after=after.replace(old,new)
old='recovery=LocalRecovery(self,spec,context,generated,plan,draft,forced=sid in forced_sections)'
new='recovery=LocalRecovery(self,spec,context,generated,plan,draft,forced=sid in forced_sections or bool(cached))'
assert after.count(old)==1;after=after.replace(old,new)
old="            checkpoint = {'generated':generated,'report':report,'source_key':(source/'lecture.tex').relative_to(self.settings.workspace).as_posix(),'source_hash':digest((source/'lecture.tex').read_bytes())}"
new="""            checkpoint = {'generated':generated,'report':report,
                'check_contract':check_contract,'check_identity':self._section_check_identity(plan,spec),
                'source_key':(source/'lecture.tex').relative_to(self.settings.workspace).as_posix(),
                'source_hash':digest((source/'lecture.tex').read_bytes())}"""
assert after.count(old)==1;after=after.replace(old,new)
destination=Path(__file__).parent
(destination/'cached-review-refresh.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(keepends=True),after.splitlines(keepends=True),
    fromfile='a/src/math_agent/pipeline.py',tofile='b/src/math_agent/pipeline.py')),encoding='utf-8')
(destination/'cached-review-refresh.candidate.py').write_text(after,encoding='utf-8')
(destination/'cached-review-refresh.base.sha256').write_text(hashlib.sha256(source.read_bytes()).hexdigest()+'\n',encoding='ascii')
print('Prepared pipeline-only patch and isolated candidate; production source unchanged.')
