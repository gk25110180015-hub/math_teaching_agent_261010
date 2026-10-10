"""Deterministic workflows; unchecked draft reuse always repeats every local check."""
import copy
import importlib.metadata
import json
import mimetypes
import platform
import re
import shutil
import zipfile
from pathlib import Path
from .compiler import TexCompiler
from .domain import LectureProposal, WrittenSection, MathReview, QUALITY_DIMENSIONS
from .provider import CompatibleChatProvider, MockProvider
from .util import AgentError, canonical, digest, now, uid, within, write_json


def question(qid, prompt, field, choices):
    return {'id': qid, 'revision': 1, 'prompt': prompt, 'selection_mode': 'single',
            'affected_fields': [field], 'blocking': True, 'reason': '此项影响写作内容，需由用户选择。',
            'options': [{'id': key, 'label': label, 'recommended': i == 0, 'effects': {'value': value}} for i,(key,label,value) in enumerate(choices)] + [{'id':'CUSTOM','label':'自定义输入','recommended':False}]}


def plain_tex(text):
    return ''.join({'\\':r'\textbackslash{}','{':r'\{','}':r'\}','%':r'\%','&':r'\&','#':r'\#','_':r'\_','$':r'\$','^':r'\textasciicircum{}','~':r'\textasciitilde{}'}.get(c,c) for c in text)


LECTURE_HEADER = r'''\documentclass[UTF8,fontset=fandol,11pt]{ctexart}
\usepackage[a4paper,margin=24mm]{geometry}
\usepackage{amsmath,amssymb,amsthm,graphicx,tabularx,booktabs,hyperref}
\newtheorem{definition}{定义}[section]
\newtheorem{theorem}[definition]{定理}
\newtheorem{example}[definition]{例题}
\newtheorem{exercise}[definition]{练习}
\hypersetup{unicode=true,colorlinks=true,linkcolor=blue}
'''


def render_lecture(title, sections, plan):
    from .parsing import _mask_verbatim, uncomment
    body, tail_answers = [], []
    exercise_prefix='mathagent:exercise:'
    for spec, generated in sections:
        body.append('\\section{' + plain_tex(spec['title']) + '}\\label{sec:'+spec['id']+'}\n')
        units = generated['units']
        by_id = {u['id']: u for u in units}
        exercise_labels={u['id']:exercise_prefix+digest([spec['id'],u['id']])
                         for u in units if u['kind']=='exercise'}
        for unit in units:
            tex, kind = unit['tex'], unit['kind']
            if re.search(r'\\label\s*\{'+re.escape(exercise_prefix),uncomment(_mask_verbatim(tex))):
                raise AgentError('RESERVED_LABEL_BLOCKED','正文使用了程序保留的练习标签前缀；保留原稿并阻止引用冲突')
            is_exercise_answer = kind == 'solution' and by_id.get(unit.get('relates_to'),{}).get('kind') == 'exercise'
            relocate_answer=is_exercise_answer and plan.get('lecture',{}).get('answers_location') == 'end'
            rendered = '% UNIT ' + unit['id'] + '\n'
            if kind in ('definition','theorem','example','exercise'):
                label='\\label{'+exercise_labels[unit['id']]+'}\n' if kind=='exercise' else ''
                rendered += f'\\begin{{{kind}}}\n{label}{tex}\n\\end{{{kind}}}\n'
            elif kind == 'proof':
                rendered += '\\begin{proof}\n' + tex + '\n\\end{proof}\n'
            elif kind == 'solution':
                if relocate_answer:
                    target=exercise_labels[unit['relates_to']]
                    heading='\\hyperref['+target+']{练习 \\ref*{'+target+'} 的解答：}'
                else:
                    heading='解：'
                rendered += '\\par\\noindent\\textbf{'+heading+'}' + tex + '\\par\n'
            else:
                rendered += tex + '\\par\n'
            if relocate_answer:
                tail_answers.append(rendered)
            else:
                body.append(rendered)
    if tail_answers:
        body += ['\\section*{练习答案}\n'] + tail_answers
    mock_label = '\\par\\noindent 离线合成演示：不代表真实模型对本专题的教学验收。\\par\n' if plan['provider'] == 'mock' else ''
    return LECTURE_HEADER + '\\title{' + plain_tex(title) + '}\n\\date{}\n\\begin{document}\n\\maketitle\n' + mock_label + ''.join(body) + '\\end{document}\n'


def visible_internal_unit_ids(tex):
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


class Pipeline:
    def __init__(self, settings, store, job):
        self.settings, self.store, self.job = settings, store, job
        self.run = store.get_run(job['run_id'])
        self.model_id = self.run['input'].get('model_id', 'gpt6')
        store.initialize_budget(job,{'requests':settings.max_requests_per_run,
            'local_repairs_per_unit':settings.max_local_repair_attempts,'global_repair_rounds':settings.max_global_repair_rounds})
        self.root = settings.workspace / 'runs' / self.run['id']
        self.root.mkdir(parents=True, exist_ok=True)
        self.build_root=settings.workspace/'b'/self.run['id'][:16]
        self.build_root.mkdir(parents=True,exist_ok=True)
        self.compiler = TexCompiler(settings.xelatex_path)
        self.provider = MockProvider() if self.run['input']['provider'] == 'mock' else CompatibleChatProvider(
            settings, before_request=lambda m: store.count_request(job, settings.max_requests_per_run, m,
                hard_limit=settings.request_budget_hard_cap),
            record=self.record, active=lambda: store.active(job),failure_dir=self.build_root/'provider-failures',
            preferred_model=self.model_id)

    @property
    def preferred_model_name(self):
        return self.settings.model if self.model_id == 'gpt6' else self.model_id

    def effective_budget(self):
        return self.store.effective_budget(self.run['id'],{'requests':self.settings.max_requests_per_run,
            'local_repairs_per_unit':self.settings.max_local_repair_attempts,'global_repair_rounds':self.settings.max_global_repair_rounds})

    def record(self, metadata):
        with self.store.transaction() as c:
            self.store.assert_fence(c, self.job)
            kind = 'provider.routing' if metadata.get('event', '').startswith(('model_', 'models_')) else 'provider.result'
            self.store.event(c, self.run['id'], kind, metadata)

    def stage(self, status, stage):
        self.store.stage(self.job, status, stage)

    def plan(self):
        self.stage('PLANNING', 'plan.propose')
        payload = self.run['input']
        base = {'schema_version':1, 'workflow_id':self.run['workflow_id'], 'input_snapshot_hash':self.run['input_hash'],
                'difficulty':payload['difficulty'], 'provider':payload['provider'], 'model_id':self.model_id, 'theme':payload['theme'],
                'decisions':[], 'decision_ids':[], 'omissions':[], 'additions':[], 'diff':[],
                'rules':{'allowed_text_sizes':['footnotesize','small','normalsize','large'], 'summary_frames':False, 'rule_version':1}}
        if self.run['workflow_id'] == 'lecture.generate':
            from .retrieval import style_context
            style=style_context(self.settings.reference_root,payload['topic'])
            proposal = self.provider.generate('planner_lecture', {**payload,'style_reference':style}, LectureProposal)
            write_json(self.root/('plan-candidate-'+uid()[:12]+'.json'),proposal)
            ids = [s['id'] for s in proposal['sections']]
            if len(ids) != len(set(ids)):
                raise AgentError('DUPLICATE_SECTION', '模型计划 section ID 不唯一')
            seen = set()
            for section in proposal['sections']:
                if not set(section['prerequisites']).issubset(seen):
                    raise AgentError('PLAN_DEPENDENCY', '计划先修关系未闭合或存在循环')
                seen.add(section['id'])
            base.update(proposal)
            from .crossrefs import reference_registry
            base['reference_registry'] = reference_registry(base)
            base['reference_context']={k:v for k,v in style.items() if k!='snippets'}
            base['lecture'] = {'proof_policy':None, 'example_focus':None, 'exercises':None, 'answers_location':None}
            base['questions'] = [
                question('Q-PROOF','定理证明采用哪种深度？','lecture.proof_policy',[('KEY','关键定理完整证明，其余说明','key'),('ALL','所有定理完整证明','all')]),
                question('Q-EXAMPLE','例题侧重什么？','lecture.example_focus',[('BALANCED','概念与计算均衡','balanced'),('ECONOMICS','更多经济应用','economics')]),
                question('Q-EXERCISE','是否安排练习与答案？','lecture.exercises',[('WITH','安排练习并附答案','with_answers'),('NONE','不安排额外练习','none')]),
                question('Q-ANSWERS','练习答案放在哪里？','lecture.answers_location',[('SECTION','各节之后','section'),('END','讲义末尾','end')])]
        else:
            parsed = payload['parsed']
            base.update(title=payload.get('topic') or Path(payload['filename']).stem,
                        sections=parsed['sections'], questions=[])
            from .beamer import theme_status
            base['template_status'] = theme_status(self.settings.reference_root)
            theme = base['template_status'].get(payload['theme'], {})
            if not theme.get('available', True):
                raise AgentError('THEME_UNAVAILABLE', '所选主题资源不完整；请补齐依赖后重试，或新建默认模板任务')
            base['theme_hash'] = theme.get('selected_sha256') or theme.get('sha256') or theme.get('hash') or theme.get('theme_hash')
            if payload['theme']=='fduclassroom':
                base['theme_adaptations']=['使用原始 FDU 主题；字号由独立适配层约束为四档。',
                    '页眉只显示当前一级章节，避免原主题长导航横向溢出；每节开始的完整三态目录保留全部一级章节。',
                    '主题原件字节保持不变；实际正文和页眉安全区仍需逐页复核。']
            base['source_issues'] = parsed.get('issues', [])
            if payload.get('source_enrichment'):
                base['source_enrichment']=payload['source_enrichment']
        base['unresolved_blocking_questions'] = [q['id'] for q in base['questions'] if q['blocking']]
        with self.store.transaction() as c:
            self.store.assert_fence(c, self.job)
            plan = self.store.save_plan(c, self.run['id'], base)
        self.store.finish(self.job, 'AWAITING_PLAN_INPUT' if base['unresolved_blocking_questions'] else 'PLAN_READY', 'plan.ready')
        return plan

    def compile(self, source, entry, build):
        if self.settings.compile_mode != 'trusted_local':
            raise AgentError('ISOLATION_UNAVAILABLE', '隔离模式尚未实现；不会自动降级为原生编译')
        return self.compiler.compile(source, entry, build, trusted=self.run['input']['trusted_input'], cancel_check=lambda: not self.store.active(self.job))

    def assert_compile(self, result):
        if result['status'] != 'PASS':
            raise AgentError('COMPILE_BLOCKED' if result['status'] == 'BLOCKED' else 'COMPILE_FAILED',
                             '本次编译未通过；日志、源码和原审批已保留：' + canonical(result.get('issues',[]))[:3000])

    def review_units(self, units, context, evidence_dir, label):
        actual={u['id'] for u in units}
        payload={**context,'units':units,'actual_unit_ids':sorted(actual)}
        plan=context.get('plan',{})
        by_id={u['id']:u for u in units}
        at_end=plan.get('lecture',{}).get('answers_location')=='end'
        payload['rendering_contract']={
            'implemented_by':'render_lecture',
            'solution_bodies_are_separate_units':True,
            'exercise_answers_at_end':at_end,
            'relocated_solution_ids':[u['id'] for u in units if at_end and u['kind']=='solution'
                and by_id.get(u.get('relates_to'),{}).get('kind')=='exercise'],
            'example_solutions_remain_inline':True,
            'instruction':'The renderer collects linked exercise solution units into the final answer section, regardless of their JSON order, when exercise_answers_at_end is true. Do not infer an answer-placement violation from unit order alone. Answers embedded in exercise.tex are NOT relocated and must still be reported. This contract is not evidence of mathematical correctness or final PDF acceptance.'}
        from .review_evidence_attribution import EvidenceAttributionGuard
        guard=EvidenceAttributionGuard(self,payload,evidence_dir,label)
        replayed=guard.replay()
        if replayed is not None:return replayed
        for attempt in range(self.settings.max_local_repair_attempts+1):
            review=self.provider.generate('reviewer_math',payload,MathReview)
            write_json(evidence_dir/f'{label}-review-{attempt}.json',review)
            invalid=sorted({i['unit_id'] for i in review['issues'] if i['unit_id'] not in actual})
            missing=sorted(actual-set(review['checked_unit_ids']))
            extra=sorted(set(review['checked_unit_ids'])-actual)
            if not invalid and not missing and not extra:
                return guard.inspect(review,accepted_payload=payload)
            payload['review_validation_feedback']={'invalid_issue_unit_ids':invalid,'unchecked_unit_ids':missing,'unknown_checked_ids':extra,
                'instruction':'Review only the supplied actual units in scope. Pending sections are not missing content in a local review. Never fabricate new unit IDs or suppress an actual in-scope mathematical error.'}
        raise AgentError('REVIEW_SCOPE_BLOCKED','审阅的单元范围或覆盖不正确；已保留全部原始审阅，不将越界问题当作正文重写依据')

    def writer_draft(self, spec, context):
        """Reuse only immutable, hash-verified writer output, never its checks.

        This is a file cache separate from Store.steps. Every return creates a
        fresh attempt directory; callers must normalize/review/compile anew.
        """
        from .provider import PROMPTS
        sid=spec['id']
        if not re.fullmatch(r'S[0-9]+',sid):
            raise AgentError('DRAFT_SECTION_ID','草稿缓存需要合法的 section ID')
        identity={'schema_version':1,'context_hash':digest(context),
            'writer_prompt_hash':digest((PROMPTS/'writer_lecture_section.md').read_bytes()),
            'written_section_schema_hash':digest(WrittenSection.model_json_schema()),
            'model':self.preferred_model_name,'provider':self.run['input']['provider']}
        cache_key=digest(identity)
        cache_path=self.root/'draft-cache'/(sid+'.json')
        generated=None; candidate_bytes=None; reused_from=None; miss_reason='NO_CACHE'
        model_provenance={'status':'UNKNOWN_NOT_RECORDED'}
        if cache_path.is_file():
            try:
                cached=json.loads(cache_path.read_text(encoding='utf-8'))
                if cached.get('cache_key')!=cache_key or cached.get('identity')!=identity:
                    miss_reason='INPUT_IDENTITY_CHANGED'
                elif cached.get('status')!='unchecked' or cached.get('section_id')!=sid:
                    miss_reason='NOT_AN_UNCHECKED_SECTION_DRAFT'
                else:
                    source=within(self.settings.workspace,cached['candidate_key'])
                    if not source.is_relative_to(self.build_root.resolve()) or source.name!='candidate.json':
                        raise ValueError('Draft is outside its controlled build directory')
                    if source.stat().st_size>8*1024*1024:
                        raise ValueError('Draft exceeds the bounded provider output size')
                    raw=source.read_bytes()
                    if digest(raw)!=cached['candidate_hash']:
                        miss_reason='CANDIDATE_HASH_CHANGED'
                    else:
                        loaded=WrittenSection.model_validate(json.loads(raw)).model_dump()
                        if loaded['section_id']!=sid:
                            raise ValueError('Cached section ID differs')
                        generated=loaded
                        candidate_bytes=raw
                        reused_from=cached['candidate_key']
                        model_provenance=cached.get('model_provenance',{'status':'UNKNOWN_NOT_RECORDED'})
            except (OSError,ValueError,KeyError,TypeError):
                miss_reason='CACHE_INVALID_OR_UNREADABLE'
        with self.store.transaction() as c:
            self.store.assert_fence(c,self.job)
            if generated is None:
                self.store.event(c,self.run['id'],'writer.draft_cache_miss',
                    {'section_id':sid,'cache_key':cache_key,'reason':miss_reason})
        if generated is None:
            generated=self.provider.generate('writer_lecture_section',context,WrittenSection)
            response_metadata=getattr(self.provider,'last_response_metadata',None) or {}
            model_provenance=({'status':'RECORDED', **{key:response_metadata[key] for key in
                ('model_id','preferred_model_id','model','base_url','call_id','input_hash','prompt_hash','prompt_version','schema_hash')
                if key in response_metadata}} if response_metadata else
                {'status':'MOCK' if self.run['input']['provider']=='mock' else 'UNKNOWN_NOT_RECORDED'})
        draft=self.build_root/('s'+sid+'_'+uid()[:12])
        draft.mkdir(parents=True,exist_ok=False)
        candidate=draft/'candidate.json'
        if candidate_bytes is None:
            write_json(candidate,generated)
            candidate_bytes=candidate.read_bytes()
        else:
            candidate.write_bytes(candidate_bytes)
        # Validate the stored content once more; no content/claim is marked checked.
        generated=WrittenSection.model_validate(json.loads(candidate_bytes)).model_dump()
        candidate_hash=digest(candidate_bytes)
        evidence={'schema_version':1,'status':'UNCHECKED_REUSED' if reused_from else 'UNCHECKED_GENERATED',
            'section_id':sid,'cache_key':cache_key,'identity':identity,'candidate_hash':candidate_hash,
            'candidate_key':candidate.relative_to(self.settings.workspace).as_posix(),
            'reused_from':reused_from,'must_rerun_checks':True,'model_provenance':model_provenance,
            'checks':['fragment_normalization','content_and_references','local_math','model_review','compile'],
            'prior_cache_miss_reason':None if reused_from else miss_reason}
        write_json(draft/'draft-reuse.json',evidence)
        with self.store.transaction() as c:
            self.store.assert_fence(c,self.job)
            if reused_from:
                self.store.event(c,self.run['id'],'writer.draft_reused',evidence)
            elif generated['section_id']==sid:
                if cache_path.is_file():
                    history=cache_path.parent/'history'/(sid+'-'+uid()[:12]+'.json')
                    history.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(cache_path,history)
                write_json(cache_path,{'schema_version':1,'status':'unchecked','section_id':sid,
                    'cache_key':cache_key,'identity':identity,'candidate_key':evidence['candidate_key'],
                    'candidate_hash':candidate_hash,'created_at':now(),'model_provenance':model_provenance,
                    'job_id':self.job['id'],'fencing_token':self.job['fencing_token']})
                self.store.event(c,self.run['id'],'writer.draft_saved',evidence)
        return generated,draft

    def _global_repair_identity(self, plan):
        from .provider import PROMPTS
        return {'plan_hash':plan['hash'],'model':self.preferred_model_name,'provider':self.run['input']['provider'],
            'repair_prompt_hash':digest((PROMPTS/'repair_content_unit.md').read_bytes()),
            'written_schema_hash':digest(WrittenSection.model_json_schema()),
            'normalizer_hash':digest(Path(__file__).with_name('lecture_fragments.py').read_bytes())}

    def _save_global_repair_state(self, state):
        path=self.root/'global-repair-state.json'
        with self.store.transaction() as c:
            self.store.assert_fence(c,self.job)
            if path.is_file():
                history=self.root/'global-repairs'/'state-history'/(uid()[:12]+'.json')
                history.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,history)
            write_json(path,state)
            self.store.event(c,self.run['id'],'global.repair_state',
                {'phase':state['phase'],'rounds_used':state['rounds_used'],
                 'pending_sections':[p['section_id'] for p in state.get('pending',[])]})

    def _global_repair_sections(self, state):
        sections={}
        try:
            for sid,record in state.get('sections',{}).items():
                path=within(self.settings.workspace,record['candidate_key'])
                if not path.is_relative_to((self.root/'global-repairs').resolve()) or not path.is_file():
                    raise ValueError('Uncontrolled repaired candidate')
                data=path.read_bytes()
                if digest(data)!=record['candidate_hash']:
                    raise ValueError('Repaired candidate hash changed')
                section=WrittenSection.model_validate(json.loads(data)).model_dump()
                if section['section_id']!=sid:
                    raise ValueError('Repaired section ID changed')
                sections[sid]=section
        except (OSError,ValueError,KeyError,TypeError):
            raise AgentError('GLOBAL_REPAIR_CACHE_INVALID','全局修复候选路径、哈希或结构失配；保留证据并阻止静默替换') from None
        return sections

    def _load_global_repair_state(self, plan):
        identity=self._global_repair_identity(plan)
        path=self.root/'global-repair-state.json'
        if path.is_file():
            try:
                state=json.loads(path.read_text(encoding='utf-8'))
                if state['identity']==identity:
                    self._global_repair_sections(state)
                    return state
                if state['identity'].get('plan_hash')==plan['hash']:
                    self._global_repair_sections(state)
                    raise AgentError('GLOBAL_REPAIR_CONTRACT_CHANGED','同一批准计划的全局修复契约发生变化；已保留原轮次、候选和疑点，不能静默归零。需恢复原契约或显式迁移状态后继续。')
            except (OSError,ValueError,KeyError,TypeError):
                raise AgentError('GLOBAL_REPAIR_CACHE_INVALID','全局修复状态不可读；已保留，不能假定通过') from None
        return {'schema_version':1,'identity':identity,'rounds_used':0,'phase':'not_started',
                'sections':{},'pending':[],'teacher_visual_review':'NOT_RUN'}

    def _start_global_repair(self, completed, issues, state):
        if state['rounds_used']>=self.effective_budget()['global_repair_rounds']:
            state.update(phase='budget_exhausted',issues=issues)
            self._save_global_repair_state(state)
            raise AgentError('BUDGET_EXHAUSTED','kind=global_repair_rounds; used='+str(state['rounds_used'])+'; limit='+str(self.effective_budget()['global_repair_rounds'])+'。保留旧疑点，不调用修复模型。')
        locations={}
        for index,(spec,section) in enumerate(completed):
            for unit in section['units']:
                if unit['id'] in locations:
                    raise AgentError('GLOBAL_REPAIR_SCOPE_UNCLEAR','跨节单元ID不唯一，不能自动定位全局修复')
                locations[unit['id']]=(index,spec['id'])
        grouped={}
        for issue in issues:
            unit_id=issue.get('unit_id')
            if unit_id not in locations:
                raise AgentError('GLOBAL_REPAIR_SCOPE_UNCLEAR','全局问题未指向实际已生成单元，不能扩大修改范围')
            grouped.setdefault(locations[unit_id][1],[]).append(issue)
        first=min(locations[i['unit_id']][0] for i in issues)
        round_number=state['rounds_used']+1
        folder=self.root/'global-repairs'/('r'+str(round_number)+'-'+uid()[:8])
        folder.mkdir(parents=True,exist_ok=False)
        state.update(rounds_used=round_number,phase='repair_pending',sections={},pending=[],
                     round_directory=folder.relative_to(self.settings.workspace).as_posix(),issues=issues)
        for index,(spec,section) in enumerate(completed):
            sid=spec['id']
            if index>=first:
                path=folder/(sid+'-before.json')
                write_json(path,section)
                state['sections'][sid]={'candidate_key':path.relative_to(self.settings.workspace).as_posix(),
                    'candidate_hash':digest(path.read_bytes())}
            if sid in grouped:
                state['pending'].append({'section_id':sid,'issues':grouped[sid],
                    'allowed_unit_ids':sorted({i['unit_id'] for i in grouped[sid]}),
                    'neighbors':[{'section':other_spec,'generated':other} for j,(other_spec,other) in enumerate(completed)
                                 if abs(j-index)==1]})
        self._save_global_repair_state(state)

    def _import_legacy_global_failure(self, plan, state, *, resume_exhausted=False):
        """Carry unresolved recorded issues forward without another reviewer lottery."""
        failure=self.root/'global_review_failure.json'
        expected_phase='budget_exhausted' if resume_exhausted else 'not_started'
        if state['phase']!=expected_phase or not failure.is_file():
            if resume_exhausted:
                raise AgentError('GLOBAL_REPAIR_LEGACY_UNVERIFIED','增额恢复所需的原全局疑点记录缺失；不重置修复状态')
            return
        try:
            raw=failure.read_bytes();record=json.loads(raw)
            issues=[i for i in record['issues'] if i.get('severity') in ('blocking','review')]
            if not issues:
                if resume_exhausted:raise ValueError('Exhausted repair lost its unresolved concerns')
                return
            if resume_exhausted and record.get('rounds_used',0)!=state['rounds_used']:
                raise ValueError('Recorded failure belongs to a different repair round')
            if record.get('plan_hash',plan['hash'])!=plan['hash']:
                raise ValueError('Recorded concern belongs to a different plan')
            completed=[];checkpoints=[]
            with self.store.connect() as c:
                for spec in plan['sections']:
                    row=c.execute('SELECT * FROM steps WHERE run_id=? AND step_key=? ORDER BY created_at DESC,rowid DESC LIMIT 1',
                        (self.run['id'],'section.'+spec['id'])).fetchone()
                    if not row:
                        raise ValueError('Missing preserved section checkpoint')
                    data=json.loads(row['output_json'])
                    if digest(data)!=row['output_hash']:
                        raise ValueError('Checkpoint hash mismatch')
                    source=within(self.settings.workspace,data['source_key'])
                    if not source.is_relative_to(self.build_root.resolve()) or digest(source.read_bytes())!=data['source_hash']:
                        raise ValueError('Preserved source hash mismatch')
                    generated=WrittenSection.model_validate(data['generated']).model_dump()
                    if generated['section_id']!=spec['id']:
                        raise ValueError('Preserved section ID mismatch')
                    completed.append((spec,generated))
                    checkpoints.append({'section_id':spec['id'],'output_hash':row['output_hash'],
                        'source_key':data['source_key'],'source_hash':data['source_hash'],
                        'generated_hash':digest(generated),'status':'UNCHECKED_SEED'})
            units={u['id']:u for _,s in completed for u in s['units']}
            if len(units)!=sum(len(s['units']) for _,s in completed):
                raise ValueError('Ambiguous unit IDs')
            if not set(record.get('checked_unit_ids',[])).issubset(units):
                raise ValueError('Old review scope no longer matches preserved units')
            if any(i.get('unit_id') not in units for i in issues):
                raise ValueError('Old concern does not identify a preserved unit')
            if resume_exhausted and state['rounds_used'] and set(record.get('unit_hashes',{}))!=set(units):
                raise ValueError('Exhausted failure does not identify the complete checked body')
            if any(k not in units or digest(units[k])!=v for k,v in record.get('unit_hashes',{}).items()):
                raise ValueError('Recorded unit hashes differ')
        except (OSError,ValueError,KeyError,TypeError):
            raise AgentError('GLOBAL_REPAIR_LEGACY_UNVERIFIED','旧全局数学疑点无法与保留单元/源文件哈希安全关联；保留疑点，不能重新抽取审阅清除') from None
        # Apply controlled migrations before measuring the model's allowed edit scope.
        # The original checkpoint body and all normalization evidence stay immutable.
        from .lecture_fragments import normalize_written_section
        seeds=self.root/'global-repairs'/('legacy-seeds-'+uid()[:12])
        canonical_completed=[]
        for (spec,generated),checkpoint in zip(completed,checkpoints):
            normalized,evidence=normalize_written_section(generated)
            raw_seed=seeds/(spec['id']+'-raw.json')
            normalized_seed=seeds/(spec['id']+'-normalized.json')
            write_json(raw_seed,generated)
            write_json(normalized_seed,normalized)
            write_json(seeds/(spec['id']+'-normalization.json'),evidence)
            if evidence['status']!='PASS':
                raise AgentError('GLOBAL_REPAIR_LEGACY_UNVERIFIED','旧稿规范化存在不明确结构；原稿及疑点保留，未扩大自动修复范围')
            checkpoint.update(raw_seed_key=raw_seed.relative_to(self.settings.workspace).as_posix(),
                raw_seed_hash=digest(raw_seed.read_bytes()),
                normalized_seed_key=normalized_seed.relative_to(self.settings.workspace).as_posix(),
                normalized_seed_hash=digest(normalized))
            canonical_completed.append((spec,normalized))
        import_evidence=self.root/'global-repairs'/('budget-resume-'+uid()[:12]+'.json' if resume_exhausted else 'legacy-failure-import.json')
        write_json(import_evidence,{
            'source_key':failure.relative_to(self.settings.workspace).as_posix(),'source_hash':digest(raw),
            'body_hashes_available':bool(record.get('unit_hashes')),'checkpoint_evidence':checkpoints,
            'issues':issues,'teacher_visual_review':'NOT_RUN',
            'limitations':[] if record.get('unit_hashes') else ['旧审阅没有正文哈希；按实际单元ID保守继承疑点，已验证checkpoint及源文件哈希，所有受影响内容仍须重新检查。']})
        rounds_before=state['rounds_used']
        requests_before=self.store.get_run(self.run['id'])['request_count']
        self._start_global_repair(canonical_completed,issues,state)
        if resume_exhausted:
            budget=self.effective_budget()
            with self.store.transaction() as connection:
                self.store.assert_fence(connection,self.job)
                self.store.event(connection,self.run['id'],'global.budget_resumed',{
                    'rounds_used_before':rounds_before,'rounds_used_after':state['rounds_used'],
                    'effective_global_limit':budget['global_repair_rounds'],'budget_version':budget['version'],
                    'request_count_preserved':requests_before,'approval_preserved':True,
                    'failure_source_hash':digest(raw),'evidence_key':import_evidence.relative_to(self.settings.workspace).as_posix(),
                    'pending_issues':issues,'teacher_review':'NOT_PERFORMED'})

    def _continue_global_repairs(self, plan, state):
        from .calculation_protocol import calculation_protocol
        from .lecture_fragments import normalize_written_section
        folder=within(self.settings.workspace,state['round_directory'])
        while state['pending']:
            request=state['pending'][0]
            sid=request['section_id'];allowed=set(request['allowed_unit_ids'])
            before=self._global_repair_sections(state)[sid]
            prefix=sid+'-'+uid()[:8]
            write_json(folder/(prefix+'-before.json'),before)
            self.stage('REPAIRING','repair.global.'+sid)
            raw=self.provider.generate('repair_content_unit',{'section':before,'issues':request['issues'],
                'allowed_unit_ids':sorted(allowed),'plan':plan,'calculation_protocol':calculation_protocol(),
                'scope':'global_interface_repair','adjacent_sections':request['neighbors'],
                'metadata_policy':'Keep all unit IDs, non-target units, their calculations and unrelated uncertainty metadata unchanged.'},WrittenSection)
            write_json(folder/(prefix+'-raw.json'),raw)
            repaired,normalization=normalize_written_section(raw)
            write_json(folder/(prefix+'-normalization.json'),normalization)
            write_json(folder/(prefix+'-normalized.json'),repaired)
            before_ids=[u['id'] for u in before['units']]
            after_ids=[u['id'] for u in repaired['units']]
            by_id={u['id']:u for u in repaired['units']}
            if (repaired['section_id']!=sid or before_ids!=after_ids
                or not allowed.issubset(before_ids)
                or any(u!=by_id.get(u['id']) for u in before['units'] if u['id'] not in allowed)):
                raise AgentError('GLOBAL_REPAIR_SCOPE_VIOLATION','全局修复改变了单元ID/顺序或未授权单元；原稿和修复稿均保留')
            old_calcs=[c for c in before.get('calculations',[]) if c.get('unit_id') not in allowed]
            new_calcs=[c for c in repaired.get('calculations',[]) if c.get('unit_id') not in allowed]
            if old_calcs!=new_calcs or before.get('uncertainties',[])!=repaired.get('uncertainties',[]):
                raise AgentError('GLOBAL_REPAIR_SCOPE_VIOLATION','全局修复改动了非目标单元核算或无关不确定性元数据')
            if normalization['status']!='PASS':
                raise AgentError('GLOBAL_REPAIR_NORMALIZATION_BLOCKED','全局修复片段存在不明确结构，不能自动采用')
            path=folder/(prefix+'-candidate.json')
            write_json(path,repaired)
            state['sections'][sid]={'candidate_key':path.relative_to(self.settings.workspace).as_posix(),
                'candidate_hash':digest(path.read_bytes())}
            state['pending'].pop(0)
            self._save_global_repair_state(state)
        state['phase']='checking'
        self._save_global_repair_state(state)

    def lecture(self, plan):
        state=self._load_global_repair_state(plan)
        if state['phase']=='budget_exhausted':
            limit=self.effective_budget()['global_repair_rounds']
            if state['rounds_used']>=limit:
                raise AgentError('BUDGET_EXHAUSTED','kind=global_repair_rounds; used='+str(state['rounds_used'])+'; limit='+str(limit)+'。需显式提高全局修复额度；原轮次、请求计数、疑点和审批均保留。')
            self._import_legacy_global_failure(plan,state,resume_exhausted=True)
        else:
            self._import_legacy_global_failure(plan,state)
        if state['pending']:
            self._continue_global_repairs(plan,state)
        while True:
            forced={} if state['phase'] in ('not_started','validated') else self._global_repair_sections(state)
            def preserve_rechecked(sid,generated):
                folder=within(self.settings.workspace,state['round_directory'])
                path=folder/(sid+'-locally-checked-'+uid()[:8]+'.json')
                write_json(path,generated)
                state['sections'][sid]={'candidate_key':path.relative_to(self.settings.workspace).as_posix(),
                    'candidate_hash':digest(path.read_bytes())}
                self._save_global_repair_state(state)
            completed,local_reports=self._lecture_sections(plan,forced,preserve_rechecked if forced else None)
            global_reports,issues=self._global_interfaces(completed,plan)
            if not issues:
                if state['rounds_used']:
                    state['phase']='validated'
                    self._save_global_repair_state(state)
                return completed,local_reports+global_reports
            failure=self.root/'global_review_failure.json'
            if failure.exists():
                archived=self.root/'global-repairs'/'failures'/(uid()[:12]+'.json')
                archived.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(failure,archived)
            write_json(failure,{'issues':issues,'reviews':global_reports,'rounds_used':state['rounds_used'],
                'plan_hash':plan['hash'],'unit_hashes':{u['id']:digest(u) for _,s in completed for u in s['units']},
                'teacher_visual_review':'NOT_RUN'})
            if state['rounds_used']>=self.effective_budget()['global_repair_rounds']:
                state['phase']='budget_exhausted'
                self._save_global_repair_state(state)
                raise AgentError('BUDGET_EXHAUSTED','kind=global_repair_rounds; used='+str(state['rounds_used'])+'; limit='+str(self.effective_budget()['global_repair_rounds'])+'。相邻章节疑点仍未解决；所有证据和原审批保留。')
            self._start_global_repair(completed,issues,state)
            self._continue_global_repairs(plan,state)

    def _section_check_contract(self):
        """Pin the checks that justify reuse; writer authorship is not a check."""
        from .provider import PROMPTS
        modules=('pipeline.py','mathcheck.py','lecture_fragments.py','crossrefs.py',
                 'parsing.py','compiler.py','compile_recovery.py','calculation_protocol.py','local_recovery.py',
                 'review_evidence_attribution.py')
        from .review_evidence_attribution import attribution_contract
        domain_checker=Path(__file__).with_name('series_domain_text.py')
        return {'schema_version':1,
            'source_hashes':{**{name:digest(Path(__file__).with_name(name).read_bytes()) for name in modules},
                'series_domain_text.py':digest(domain_checker.read_bytes()) if domain_checker.is_file() else 'MISSING'},
            'reviewer_prompt_hash':digest((PROMPTS/'reviewer_math.md').read_bytes()),
            'review_schema_hash':digest(MathReview.model_json_schema()),
            'review_attribution_contract':attribution_contract(),
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

    def _section_recheck_seed(self, spec, saved, plan):
        """Prefer any later accepted local repair; never roll back to old PASS."""
        state_path=self.root/'local-repair'/(spec['id']+'.json')
        if not state_path.exists():return copy.deepcopy(saved['generated']) if saved is not None else None
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

    def _unchecked_section_recheck_seed(self, spec, context, plan):
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

    def _lecture_sections(self, plan, forced_sections=None, on_rechecked=None):
        from .mathcheck import check_math
        from .calculation_protocol import calculation_protocol
        from .lecture_fragments import normalize_written_section
        from .parsing import preflight_tex
        from .crossrefs import inspect_section_references, local_reference_gate
        completed, local_reports = [], []
        forced_sections=forced_sections or {}
        check_contract=self._section_check_contract()
        checkpoints=self._verified_section_checkpoints(plan)
        for spec in plan['sections']:
            sid = spec['id']
            self.stage('BUILDING', 'write.section.' + sid)
            cache_key=self._section_input_hash(plan,spec,completed)
            snapshot=checkpoints.get(sid)
            cached=snapshot['output'] if snapshot else None
            if (cached and sid not in forced_sections and snapshot['input_hash']==cache_key
                    and cached.get('check_contract')==check_contract):
                completed.append((spec,cached['generated']))
                local_reports.append(cached['report'])
                continue
            from .retrieval import style_context
            context = {'section':spec, 'plan':plan, 'completed_sections':[g for _,g in completed], 'topic':self.run['input']['topic'], 'difficulty':plan['difficulty'],
                       'style_reference':style_context(self.settings.reference_root,self.run['input']['topic']),
                       'calculation_protocol':calculation_protocol()}
            unchecked_seed=(self._unchecked_section_recheck_seed(spec,context,plan)
                if sid not in forced_sections and not cached else None)
            if sid in forced_sections:
                generated=copy.deepcopy(forced_sections[sid])
                draft=self.build_root/('s'+sid+'_'+uid()[:12])
                draft.mkdir(parents=True,exist_ok=False)
                write_json(draft/'candidate.json',generated)
                write_json(draft/'global-repair-recheck.json',{'section_id':sid,'status':'UNCHECKED',
                    'candidate_hash':digest(generated),'reason':'Recheck affected section and all following sections without reauthoring'})
            elif cached:
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
            elif unchecked_seed is not None:
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
            generated, normalization = normalize_written_section(generated)
            write_json(draft/'candidate-normalization.json', normalization)
            write_json(draft/'candidate-normalized.json', generated)
            from .local_recovery import LocalRecovery,issue_targets
            recovery=LocalRecovery(self,spec,context,generated,plan,draft,forced=sid in forced_sections or bool(cached) or unchecked_seed is not None)
            resumed=recovery.candidate()
            if resumed['units']!=generated['units']:
                generated,normalization=normalize_written_section(resumed)
                write_json(draft/'local-resume-normalization.json',normalization)
            else:generated=resumed
            report = None
            label_recovery = recovery.state.get('reference_recovery')
            answer_recovery = recovery.state.get('answer_recovery')
            attempt=0
            compile_history=[]
            while True:
                layout_repair=bool(recovery.state.get('pending_compile_layout'))
                self.stage('LOCAL_REVIEW', 'review.section.' + sid)
                issues = self.validate_written(spec, generated, plan)
                issues.extend(normalization['issues'])
                references = inspect_section_references(spec, generated, completed, plan)
                issues.extend(references['issues'])
                for unit in generated['units']:
                    issues.extend({**issue,'unit_id':unit['id']} for issue in preflight_tex(unit['tex']))
                math = check_math(generated)
                issues.extend(math.get('issues', []))
                review_identity,recovery_context=recovery.review_context(generated,math,
                    {'issues':copy.deepcopy(issues),
                     # Transformation history/raw spans differ after cache restoration;
                     # only the checker version and actual outcome justify re-review.
                     'normalization':{k:normalization[k] for k in ('schema_version','status','issues')},
                     'references':references})
                review = self.review_units(generated['units'], {'plan':plan,'prior_sections':[g for _,g in completed],'tool_checks':math,
                    'reference_recovery':label_recovery,'local_recovery':recovery_context,
                    'scope':{'kind':'section_local','current_section':spec,'pending_sections':[s['id'] for s in plan['sections'] if s['id'] not in {x['id'] for x,_ in completed} and s['id']!=sid]}},draft,f'local-{attempt}')
                if set(review['checked_unit_ids']) != {u['id'] for u in generated['units']}:
                    issues.append({'rule_id':'REVIEW_COVERAGE','severity':'blocking','message':'审阅未覆盖全部实际单元'})
                issues.extend(review['issues'])
                if generated.get('uncertainties'):
                    issues.extend({'severity':'review','message':i} for i in generated['uncertainties'])
                report = {'section_id':sid,'math':math,'llm_review':review, 'issues':issues,
                    'reference_recovery':label_recovery,'answer_recovery':answer_recovery,
                    'mock':self.run['input']['provider']=='mock'}
                blocking=recovery.record_review(issues,review_identity,report)
                report['issues']=issues+[i for i in blocking if i not in issues]
                report['local_recovery']={'applied_rounds':recovery.state['applied_rounds'],
                    'proposal_calls':recovery.state['proposal_calls'],'rejected_proposals':recovery.state['rejected_proposals'],
                    'preserved_issues':recovery_context['unresolved_issues'],'review_identity':review_identity}
                write_json(draft/f'review-{attempt}.json',report)
                if not blocking:
                    from .compile_recovery import compile_section_attempt, persist_compile_doubt
                    compiled_attempt=compile_section_attempt(self,spec,generated,completed,plan,draft,attempt,references)
                    source=compiled_attempt['source']
                    compile_result=compiled_attempt['compile']
                    reference_check=compiled_attempt['references']
                    compile_history.append(compiled_attempt['evidence'])
                    report['compile']=compile_result
                    report['references']=reference_check
                    report['compile_attempts']=copy.deepcopy(compile_history)
                    if not compiled_attempt['repair_issues']:
                        if recovery.state.pop('pending_compile_layout',None) is not None:
                            recovery.save()
                        break
                    blocking=persist_compile_doubt(recovery,compiled_attempt,review_identity,report)
                    report['issues']+=compiled_attempt['repair_issues']
                    layout_repair=True
                    write_json(draft/f'compile-review-{attempt}.json',report)
                layout_repair=layout_repair or any(i.get('rule_id')=='OVERFULL_BOX' for i in blocking)
                label_missing=any(i.get('rule_id')=='PLANNED_LABEL_MISSING' for i in blocking)
                answer_missing=any(i.get('rule_id')=='MISSING_ASSOCIATED_ANSWER' for i in blocking)
                if self.run['input']['provider']=='mock' and not label_missing:
                    raise AgentError('MATH_REVIEW_BLOCKED', '本节存在数学/内容疑点，已保留草稿：'+canonical(blocking)[:2000])
                target_ids=set() if label_missing or answer_missing else issue_targets(blocking)
                if not target_ids.issubset({u['id'] for u in generated['units']}):
                    raise AgentError('REPAIR_SCOPE_UNCLEAR','问题定位到未提供的单元，不能扩大修改范围')
                if label_missing:
                    from .reference_recovery import missing_planned_labels
                    budget_keys=['label:'+label for label in missing_planned_labels(spec,generated)]
                elif answer_missing:
                    budget_keys=['answer:'+i['unit_id'] for i in blocking if i.get('rule_id')=='MISSING_ASSOCIATED_ANSWER']
                else:budget_keys=['unit:'+unit_id for unit_id in target_ids]
                proposal_number=recovery.begin_proposal('labels' if label_missing else 'answers' if answer_missing else 'strict_local_patch',budget_keys,target_ids)
                before=generated
                try:
                    if label_missing:
                        from .reference_recovery import recover_planned_labels
                        generated,label_recovery=recover_planned_labels(self,spec,before,completed,plan,draft,proposal_number)
                        label_recovery['review_instruction']='必须核对标签是否对应其引用定义和批准小节目标；精确引文不代表概念正确。否定形式不能代替正面定义。定位不当须报告实际 unit_id，不能只因标签存在而放行。'
                        generated,normalization=normalize_written_section(generated)
                        write_json(draft/f'label-repair-{proposal_number}-normalization.json',normalization)
                    elif answer_missing:
                        from .answer_recovery import recover_missing_answers
                        generated,answer_recovery=recover_missing_answers(self,spec,before,completed,plan,draft,proposal_number)
                        generated,normalization=normalize_written_section(generated)
                        write_json(draft/f'answer-repair-{proposal_number}-normalization.json',normalization)
                    else:
                        from .local_patch import LocalPatch,apply_local_patch
                        self.stage('REPAIRING','repair.section.'+sid)
                        raw=self.provider.generate('repair_local_patch',{'section':before,'issues':blocking,
                            'allowed_unit_ids':sorted(target_ids),'plan':plan,'calculation_protocol':calculation_protocol(),
                            'remaining_unit_modifications':{i:self.effective_budget()['local_repairs_per_unit']-recovery.state['unit_applied_counts'].get(i,0) for i in target_ids}},LocalPatch)
                        write_json(draft/f'repair-{proposal_number}-patch.json',raw)
                        generated,patch_evidence=apply_local_patch(before,target_ids,raw)
                        selected={**generated,'units':[copy.deepcopy(u) for u in generated['units'] if u['id'] in target_ids]}
                        normalized,normalization=normalize_written_section(selected)
                        normalized_by_id={u['id']:u['tex'] for u in normalized['units']}
                        for unit in generated['units']:
                            if unit['id'] in normalized_by_id:unit['tex']=normalized_by_id[unit['id']]
                        write_json(draft/f'repair-{proposal_number}-evidence.json',patch_evidence)
                        patch_evidence['proposal_key']=(draft/f'repair-{proposal_number}-patch.json').relative_to(self.settings.workspace).as_posix()
                        write_json(draft/f'repair-{proposal_number}-normalization.json',normalization)
                    if layout_repair:
                        from .compile_recovery import reject_layout_suppression
                        reject_layout_suppression(before,generated,target_ids)
                    if normalization['status']!='PASS':
                        raise AgentError('REPAIR_SCOPE_VIOLATION','局部候选结构不明确，未采用；合法原稿和提案保留')
                except (ValueError,AgentError) as exc:
                    code=getattr(exc,'code','REPAIR_SCOPE_VIOLATION')
                    if isinstance(exc,ValueError) or code in {'INVALID_MODEL_JSON','REPAIR_SCOPE_VIOLATION','ANSWER_COMPLETION_BLOCKED'} or code.startswith('LABEL_MAPPING'):
                        recovery.reject(exc)
                    else:
                        recovery.state['phase']='PROPOSAL_INTERRUPTED';recovery.save()
                    if isinstance(exc,ValueError):
                        raise AgentError('REPAIR_SCOPE_VIOLATION','局部补丁超出授权范围或协议：'+str(exc)[:500]) from None
                    raise
                recovery.accept(generated,reference_recovery=label_recovery,answer_recovery=answer_recovery,
                    patch_evidence=patch_evidence if not label_missing and not answer_missing else None)
                write_json(draft/f'repair-{proposal_number}.json',{'before_hash':digest(before),'after_hash':digest(generated),'section':generated})
                attempt+=1
            report['compile']=compile_result
            report['references']=reference_check
            checkpoint = {'generated':generated,'report':report,
                'check_contract':check_contract,'check_identity':self._section_check_identity(plan,spec),
                'source_key':(source/'lecture.tex').relative_to(self.settings.workspace).as_posix(),
                'source_hash':digest((source/'lecture.tex').read_bytes())}
            self.store.checkpoint(self.job,'section.'+sid,cache_key,checkpoint)
            recovery.checked()
            if on_rechecked and sid in forced_sections:
                on_rechecked(sid,generated)
            completed.append((spec,generated))
            local_reports.append(report)
        return completed,local_reports

    def _recheck_feedback(self, plan):
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

    def _global_interfaces(self, completed, plan):
        self.stage('GLOBAL_REVIEW','math.global_interfaces')
        global_reports=[];issues=[]
        review_cycle=uid()[:8]
        if [spec['id'] for spec,_ in completed]!=[spec['id'] for spec in plan['sections']]:
            raise AgentError('INCOMPLETE_CHAPTER_REVIEW','全章语义检查需要全部批准章节的实际正文，不能以部分稿认定目标覆盖')
        # Check actual complete bodies plus each adjacent dependency interface.
        seen={}
        for _,generated in completed:
            for u in generated['units']:
                if u['kind'] in ('definition','theorem','example','exercise'):
                    key=digest(''.join(u['tex'].split()))
                    if key in seen:
                        raise AgentError('DUPLICATE_CONTENT_BLOCKED','重复数学单元：'+seen[key]+' 与 '+u['id'])
                    seen[key]=u['id']
        for i in range(len(completed)-1):
            units=completed[i][1]['units']+completed[i+1][1]['units']
            review=self.review_units(units,{'plan':plan,'prior_sections':[g for _,g in completed[:i]],
                'scope':{'kind':'adjacent_interface','sections':[completed[i][0]['id'],completed[i+1][0]['id']],
                'instruction':'Check actual adjacent bodies and their dependency interface. Other plan sections are outside this pair; full coverage is checked separately.'}},self.root,'global-'+review_cycle+'-'+str(i))
            issues.extend(issue for issue in review['issues'] if issue['severity'] in ('blocking','review'))
            global_reports.append({'global_interface':[completed[i][0]['id'],completed[i+1][0]['id']],'review':review})
        if not issues and completed:
            self.stage('GLOBAL_REVIEW','teaching.chapter_coverage')
            section_unit_map=[{'section_id':spec['id'],'title':spec['title'],
                'objectives':spec.get('objectives',[]),'unit_ids':[u['id'] for u in generated['units']]}
                for spec,generated in completed]
            units=[u for _,generated in completed for u in generated['units']]
            context={'plan':plan,'section_unit_map':section_unit_map,
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
        return global_reports,issues

    def validate_written(self, spec, data, plan):
        issues = []
        units = data['units']; ids = [u['id'] for u in units]; kinds = {u['kind'] for u in units}
        if data['section_id'] != spec['id'] or len(ids)!=len(set(ids)):
            issues.append({'severity':'blocking','message':'section/单元 ID 不匹配'})
        for k in spec.get('required_kinds',[]):
            if k not in kinds:
                issues.append({'severity':'blocking','message':'未生成计划要求的 '+k})
        for u in units:
            leaked_ids=visible_internal_unit_ids(u['tex'])
            if leaked_ids:
                issues.append({'rule_id':'INTERNAL_UNIT_ID_VISIBLE','severity':'blocking','unit_id':u['id'],
                    'message':'学生正文出现内部单元ID '+', '.join(leaked_ids)+'；保留数学内容，改为自然名称或已存在且语义正确的编号引用，不得编造标签。',
                    'evidence':leaked_ids})
            if re.search(r'\\(?:documentclass|usepackage|RequirePackage|newcommand|renewcommand|def|gdef|global|section|subsection|input|include)(?![A-Za-z@])|\\(?:begin|end)\{document\}',u['tex']):
                issues.append({'severity':'blocking','unit_id':u['id'],'message':'内容单元越过片段边界，尝试修改全局模板/宏/章节或读取文件'})
            if u['kind'] in ('example','exercise') and not any(v['kind']=='solution' and v.get('relates_to')==u['id'] for v in units):
                issues.append({'rule_id':'MISSING_ASSOCIATED_ANSWER','severity':'blocking','unit_id':u['id'],'message':'例题/练习缺少显式关联答案'})
            if u['kind']=='theorem' and plan.get('lecture',{}).get('proof_policy')=='all' and not any(v['kind']=='proof' and v.get('relates_to')==u['id'] for v in units):
                issues.append({'severity':'blocking','unit_id':u['id'],'message':'用户选择全部证明，但此定理缺少证明'})
        exercises = plan.get('lecture',{}).get('exercises')
        if exercises=='none' and 'exercise' in kinds:
            issues.append({'severity':'blocking','message':'用户排除练习但实际新增了练习'})
        if exercises=='with_answers' and 'exercise' not in kinds:
            issues.append({'severity':'blocking','message':'用户要求练习，但实际缺失'})
        return issues

    def build(self):
        from .pdfcheck import inspect_pdf
        plan = self.run['plan']
        if not self.run['approval'] or self.run['approval']['hash'] != plan['hash']:
            raise AgentError('APPROVAL_REQUIRED','worker 不能自行确认计划')
        if plan.get('theme')=='fduclassroom':
            from .beamer import theme_status
            current_theme=theme_status(self.settings.reference_root)['fduclassroom']
            if not current_theme.get('available') or current_theme.get('selected_sha256')!=plan.get('theme_hash'):
                raise AgentError('THEME_CHANGED_BLOCKED','FDU 主题在审批后改变；本次未构建，请恢复原主题或重新规划')
        output = self.build_root/('v'+uid()[:12])
        output.mkdir(parents=True)
        write_json(self.root/'latest_build.json',{'storage_key':output.relative_to(self.settings.workspace).as_posix(),'plan_revision':plan['revision'],'plan_hash':plan['hash'],'status':'draft'})
        source=output/'source'; source.mkdir()
        quality = {k:{'status':'NOT_RUN','evidence':[],'limitations':[]} for k in QUALITY_DIMENSIONS}
        quality.update(schema_version=1, provider=self.run['input']['provider'], human_visual_review='NOT_RUN', model_visual_review='NOT_RUN', issues=[])
        beamer = self.run['workflow_id']=='beamer.from_tex'
        rendered = None; local_reports=[]; compiled=None
        if not beamer:
            sections, local_reports = self.lecture(plan)
            entry='lecture.tex'
            (source/entry).write_bytes(render_lecture(plan['title'],sections,plan).encode('utf-8'))
            quality['content']={'status':'PASS','evidence':['计划必需类型、题解关联及各节局部检查'], 'limitations':['课程难度与经济应用等语义要求需教师审核']}
            math_pending=self.run['input']['provider']=='mock' or any(r.get('math',{}).get('status','PASS')!='PASS' for r in local_reports)
            quality['math']={'status':'NEEDS_REVIEW' if math_pending else 'PASS', 'evidence':local_reports,'limitations':['同模型分角色审阅不是形式化证明；未支持或未请求的核算仍需人工复核']}
            quality['fidelity']={'status':'NOT_APPLICABLE','evidence':[], 'limitations':[]}
            write_json(output/'source_map.json',{'sections':[{'id':s['id'],'units':[u['id'] for u in g['units']]} for s,g in sections]})
        else:
            from .beamer import render_beamer, check_fidelity
            entry='slides.tex'
            parsed=self.run['input']['parsed']
            candidate_results=[]
            for idx, layout in enumerate([{'split_long':True},{'font_size':'normalsize','split_long':False},{'font_size':'small','split_long':False},{'font_size':'footnotesize','split_long':False},{'font_size':'footnotesize','split_long':True}]):
                self.stage('BUILDING',f'layout.candidate.{idx+1}')
                candidate=output/f'candidate-{idx+1}'
                candidate.mkdir()
                render_plan={**plan,'_layout':layout}
                rendered=render_beamer(parsed,render_plan,candidate,self.settings.reference_root)
                issues=rendered.get('issues',[])
                fidelity=check_fidelity(parsed,{**plan,'_render_scaffold_hash':rendered.get('render_scaffold_hash')},(candidate/entry).read_text(encoding='utf-8'))
                write_json(output/f'fidelity-{idx+1}.json',fidelity)
                quality['fidelity']=fidelity
                quality['issues']=issues+fidelity.get('issues',[])
                if fidelity.get('status')=='FAIL' or any(i.get('severity','blocking')=='blocking' for i in issues):
                    source=candidate
                    break
                self.stage('LOCAL_REVIEW',f'compile.layout.{idx+1}')
                compiled=self.compile(candidate,entry,output/f'build-{idx+1}')
                candidate_results.append({'layout':layout,'compile':compiled})
                write_json(output/'layout_candidates.json',candidate_results)
                source=candidate
                if compiled['status']=='PASS':
                    break
                # Only layout overflow is reparable by font/semantic refinement.
                if any(i.get('rule_id')!='OVERFULL_BOX' and i.get('severity')=='blocking' for i in compiled.get('issues',[])):
                    break
            quality['content']={'status':'PASS' if fidelity.get('status')=='PASS' else 'FAIL','evidence':['实际 TeX 与保留源单元对照'],'limitations':[]}
            quality['math']={'status':'NEEDS_REVIEW','evidence':['原文保真；未自动修正源讲义数学结论'],'limitations':['教师须复核原文的具体数学疑点']}
            for name in ('source_map','frame_plan','layout_plan'):
                write_json(output/(name+'.json'),rendered.get(name,{}))
        self.stage('GLOBAL_REVIEW','compile.global')
        if compiled is None:
            if not any(i.get('severity','blocking')=='blocking' for i in quality['issues']):
                compiled=self.compile(source,entry,output/'build')
            else:
                compiled={'status':'BLOCKED','issues':quality['issues'],'pdf_path':None}
        quality['compile']=compiled
        quality['issues'].extend(compiled.get('issues',[]))
        pdf_result=None
        if compiled.get('pdf_path'):
            pdf_path=Path(compiled['pdf_path'])
            if rendered:
                frames=rendered.get('frame_plan',[])
                if isinstance(frames,dict):
                    frames=frames.get('frames',[])
                frame_ids=[f.get('frame_id',f.get('id',f'F{i+1:03}')) for i,f in enumerate(frames)]
                if frame_ids:
                    (pdf_path.parent/'frame_ids.txt').write_text('\n'.join(frame_ids),encoding='utf-8')
            self.stage('GLOBAL_REVIEW','render.all_pages')
            pdf_result=inspect_pdf(pdf_path,output/'pages',beamer=beamer)
            write_json(output/'pdf_inspection.json',pdf_result)
            quality['layout']={'status':pdf_result['status'],'evidence':{'page_count':pdf_result['page_count'],'all_rendered':len(pdf_result['pages'])==pdf_result['page_count']},'limitations':pdf_result.get('limitations',[])}
            quality['issues'].extend(pdf_result.get('issues',[]))
            if beamer:
                write_json(output/'overlay_map.json',pdf_result.get('overlay_map',{}))
                # Section checkpoints are tied to the actual compiled document and all its
                # physical overlay pages; a model's claimed source map is insufficient.
                if compiled['status']=='PASS' and fidelity.get('status')=='PASS' and not any(i.get('severity')=='blocking' for i in quality['issues']):
                    frames=rendered.get('frame_plan',[])
                    if isinstance(frames,dict):frames=frames.get('frames',[])
                    actual_map=pdf_result.get('overlay_map',{}).get('pages',[])
                    for section in plan['sections']:
                        section_frames={f.get('frame_id',f.get('id')) for f in frames if f.get('section_id')==section['id']}
                        physical=[p['physical_page'] for p in actual_map if p['frame_id'] in section_frames]
                        if physical:
                            self.store.checkpoint(self.job,'beamer.section.'+section['id'],digest([plan['hash'],section,rendered.get('theme_hash'),'rules-v1']),
                                {'source_unit_ids':section.get('source_unit_ids',[]),'physical_pages':physical,'fidelity':'PASS',
                                 'compile':'PASS','pdf_hash':digest(pdf_path.read_bytes()),'visual_review':'NEEDS_REVIEW',
                                 'source_key':(source/entry).relative_to(self.settings.workspace).as_posix()})
        coverage=self.decision_coverage(plan,source/entry,quality)
        quality['policy']={'status':'NEEDS_REVIEW' if any(x['status']=='NEEDS_REVIEW' for x in coverage['decisions']) else 'PASS','evidence':coverage,'limitations':[]}
        quality['security']={'status':'PASS' if compiled.get('status')=='PASS' else 'NOT_RUN','evidence':['回环服务、受控源码、编译参数及白名单子进程环境'],'limitations':['trusted_local 不是文件系统/网络隔离沙箱']}
        write_json(output/'decision_coverage.json',coverage)
        write_json(output/'plan.json',plan)
        write_json(output/'quality_report.json',quality)
        (output/'quality_report.md').write_text('# 质量报告\n\n'+ '\n'.join(f'- {k}: {quality[k].get("status", "NOT_RUN")}' for k in QUALITY_DIMENSIONS)+'\n\n人工视觉复核：NOT_RUN（须在界面逐页确认，并审阅此报告）。\n真实模型视觉复核：NOT_RUN。\n',encoding='utf-8')
        self.export_source(source,entry,output,plan,compiled)
        artifacts=[]
        deliver=[p for p in output.iterdir() if p.is_file() and p.suffix in ('.json','.md','.zip')]
        deliver.append(source/entry)
        if compiled.get('pdf_path'):
            deliver.append(Path(compiled['pdf_path']))
        if pdf_result:
            deliver += [Path(p['image_path']) for p in pdf_result['pages']]
        page_meta={str(Path(p['image_path']).resolve()):p for p in (pdf_result or {}).get('pages',[])}
        for p in deliver:
            if p.is_file():
                metadata=page_meta.get(str(p.resolve()),{})
                artifacts.append({'storage_key':p.relative_to(self.settings.workspace).as_posix(),'name':p.name,'sha256':digest(p.read_bytes()),'media_type':mimetypes.guess_type(p.name)[0] or 'application/octet-stream',
                                  'metadata':{k:v for k,v in metadata.items() if k not in ('image_path',)}})
        self.store.publish_artifacts(self.job,artifacts)
        blocking=compiled.get('status')!='PASS' or any(i.get('severity')=='blocking' for i in quality['issues']) or quality['fidelity'].get('status')=='FAIL' or quality['layout'].get('status')=='FAIL'
        if blocking:
            raise AgentError('QUALITY_BLOCKED','本次构建存在未通过门禁；草稿、日志与已完成章节保留，请查看质量报告后重试')
        self.store.finish(self.job,'AWAITING_USER_REVIEW','review.pages_and_quality')
        return output

    def decision_coverage(self, plan, tex_path, quality):
        text=tex_path.read_text(encoding='utf-8')
        evidence=[]
        for d in plan.get('decisions',[]):
            fields=d.get('affected_fields',[])
            semantic=any(f in ('lecture.example_focus','lecture.proof_policy') for f in fields) or 'CUSTOM' in d.get('selected_option_ids',[])
            evidence.append({'decision_id':d['id'],'resolved_effects':d.get('resolved_effects',d.get('resolved')),
                             'status':'NEEDS_REVIEW' if semantic else 'PASS',
                             'artifact':tex_path.name,'artifact_hash':digest(text),
                             'evidence':'需教师检查具体语义是否落实' if semantic else '范围/练习/题解/答案位置由确定性渲染和来源检查落实'})
        return {'schema_version':1,'decisions':evidence,'limitations':['语义自定义不能仅凭模型自评当作落实；发布前须人工审阅质量报告。']}

    def export_source(self, source, entry, output, plan,compiled=None):
        (output/'SOURCE_README.md').write_text('本地私人使用的完整源包。主文件 '+entry+'。使用 XeLaTeX 连续编译至少两遍，需 TeX Live、ctex、Fandol、amsmath 和主题相应依赖。无需模型密钥。FDU 和用户图片的许可未核定，不据此公开分发。\n',encoding='utf-8')
        from .model_evidence import routing_summary
        model_routing = routing_summary(self.store, self.run)
        manifest={'schema_version':1,'created_at':now(),'python':platform.python_version(),'platform':platform.platform(),'input_hash':self.run['input_hash'],'plan_hash':plan['hash'],'rule_version':1,'model':self.preferred_model_name,'model_field_meaning':'preferred_model_not_exclusive_authorship','model_routing':model_routing,'provider':self.run['input']['provider'],'font':'Fandol','theme_hash':plan.get('theme_hash'),'files':[],
                  'compiler':{k:v for k,v in (compiled or {'status':'NOT_RUN'}).items() if k in ('status','engine','passes','engine_version')},
                  'dependencies':{name:importlib.metadata.version(name) for name in ('fastapi','pydantic','httpx','sympy','pypdfium2','pdfplumber','pylatexenc')}}
        with zipfile.ZipFile(output/'source_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(source.rglob('*')):
                if p.is_file() and p.suffix.lower() in ('.tex','.sty','.cls','.png','.jpg','.jpeg','.pdf','.eps','.pgf','.tikz'):
                    rel=p.relative_to(source).as_posix()
                    z.write(p,rel)
                    manifest['files'].append({'path':rel,'sha256':digest(p.read_bytes())})
            z.write(output/'SOURCE_README.md','README.md')
        manifest['source_bundle_sha256']=digest((output/'source_bundle.zip').read_bytes())
        if compiled and compiled.get('pdf_path') and Path(compiled['pdf_path']).exists():
            manifest['pdf_sha256']=digest(Path(compiled['pdf_path']).read_bytes())
        lock=Path(__file__).resolve().parents[2]/'uv.lock'
        manifest['dependency_lock_sha256']=digest(lock.read_bytes()) if lock.exists() else None
        write_json(output/'build_manifest.json',manifest)
