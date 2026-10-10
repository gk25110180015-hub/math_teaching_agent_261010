"""Auditable local benchmark measurements, never a mathematical or teacher verdict."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import statistics
import threading
import time

from .util import AgentError, digest, scrub, within, write_json


CASES = {
    'smoke': {'dataset': 'CH01', 'directory': '第一章', 'topic': '数列极限入门。此为小型基准测试，严格只规划两节：数列极限的定义与唯一性；简单数列极限及运算。每节安排一个例题及一个练习，避免扩展为整章。', 'min_sections': 2, 'max_sections': 2},
    'CH01': {'dataset': 'CH01', 'directory': '第一章', 'topic': '数列与数列极限。覆盖数列极限定义、性质、运算法则、夹逼与单调有界原理，规划4至6节完整的本科入门讲义，每节至少一个例题和一个练习。', 'min_sections': 4, 'max_sections': 6},
    'CH02': {'dataset': 'CH02', 'directory': '第二章', 'topic': '无穷级数。覆盖级数与部分和、收敛的必要条件、正项级数判别、交错级数、绝对与条件收敛，规划4至6节完整的本科入门讲义，每节至少一个例题和一个练习。', 'min_sections': 4, 'max_sections': 6},
    'CH03': {'dataset': 'CH03', 'directory': '第三章', 'topic': '函数极限与连续。覆盖函数极限定义、左右极限与无穷远极限、极限性质与运算、无穷小和连续性，规划4至6节完整的本科入门讲义，每节至少一个例题和一个练习。', 'min_sections': 4, 'max_sections': 6},
}
CHOICES = {'Q-PROOF':'KEY', 'Q-EXAMPLE':'BALANCED', 'Q-EXERCISE':'WITH', 'Q-ANSWERS':'END'}
KIND_ALIASES = {'example_statement':'example', 'example_solution':'solution', 'proposition':'theorem', 'corollary':'theorem', 'property':'theorem'}
CONDITION_PATTERNS = {
    'universal_quantifier': r'任意|任取|对每|所有|\\forall\b',
    'existential_quantifier': r'存在|\\exists\b',
    'domain': r'定义域|区间|邻域|实数|复数|整数|x\\in|n\\in',
    'nonzero': r'非零|不为零|不等于零|\\ne(?:q)?\s*0|\\neq\s*0',
    'continuity': r'连续', 'differentiability': r'可导|可微',
    'monotonicity': r'单调|递增|递减', 'boundedness': r'有界|上界|下界',
    'positivity': r'正项|正实数|非负',
}


def unit_metrics(units: list[dict], sections: list[dict] | None = None, prerequisites: list | None = None) -> dict:
    """Count observable structure and lexical cues; do not infer semantic completeness."""
    active = [u for u in units if u.get('kind') != 'presentation_scaffold' and u.get('source_visibility') != 'inactive']
    by_id = {u['id']: u for u in active}
    raw = Counter(u.get('kind', 'unknown') for u in active)
    normalized = Counter(KIND_ALIASES.get(u.get('kind'), u.get('kind', 'unknown')) for u in active)
    cues, exercise_links, condition_evidence = Counter(), [], []
    for unit in active:
        text = unit.get('tex', unit.get('raw_tex', ''))
        for name, pattern in CONDITION_PATTERNS.items():
            matches = list(re.finditer(pattern, text))
            if matches:
                cues[name] += len(matches)
                condition_evidence.append({'unit_id':unit['id'], 'marker':name, 'occurrences':len(matches), 'unit_hash':digest(text)})
        rel = unit.get('semantic_relations', {})
        target = unit.get('relates_to') or (rel.get('solution_of') if isinstance(rel, dict) else None)
        if KIND_ALIASES.get(unit.get('kind'), unit.get('kind')) == 'solution' and by_id.get(target, {}).get('kind') == 'exercise':
            exercise_links.append({'solution':unit['id'], 'exercise':target})
    section_data = sections or []
    return {
        'status':'MEASURED', 'unit_count':len(active), 'raw_kind_counts':dict(sorted(raw.items())),
        'normalized_kind_counts':dict(sorted(normalized.items())),
        'normalization':KIND_ALIASES, 'section_count':len(section_data),
        'section_titles':[s.get('title', '') for s in section_data],
        'explicit_global_prerequisites':prerequisites or [],
        'explicit_section_prerequisites':[{'section_id':s['id'], 'prerequisites':s.get('prerequisites', [])} for s in section_data],
        'source_reference_dependencies':[{'unit_id':u['id'], 'targets':u['dependencies']} for u in active if u.get('dependencies')],
        'condition_marker_counts':dict(cues), 'condition_evidence':condition_evidence,
        'exercise_strategy':{'exercise_units':normalized.get('exercise',0), 'explicit_exercise_solution_links':exercise_links, 'answer_placement':'NOT_INFERRED_FROM_COUNTS'},
        'limitations':['类型归一仅供比较；原始类型计数同时保留。', '先修字段、交叉引用依赖与条件词出现次数不等同于数学条件完整性或正确性。', '未匹配的题解关系可能是源解析粒度限制，不能断言没有答案。'],
    }


def page_metrics(inspection: dict | None) -> dict:
    if not inspection:
        return {'status':'NOT_RUN', 'page_count':None, 'pages':[], 'mean_characters_per_page':None}
    pages = []
    for page in inspection.get('pages', []):
        g = page['geometry']
        area_cm2 = g['page_width_pt'] * g['page_height_pt'] * (2.54 / 72) ** 2
        pages.append({'physical_page':page['physical_page'], 'characters':g['character_count'],
            'characters_per_100cm2':round(g['character_count'] / area_cm2 * 100, 3),
            'text_bbox_pt':g.get('text_bbox_pt'), 'image_count':g.get('image_count'),
            'image_sha256':page.get('sha256')})
    counts = [p['characters'] for p in pages]
    return {'status':'MEASURED' if len(pages) == inspection.get('page_count') else 'PARTIAL',
        'inspection_status':inspection.get('status'), 'page_count':inspection.get('page_count'), 'pages':pages,
        'mean_characters_per_page':round(statistics.mean(counts), 3) if counts else None,
        'minimum_characters_per_page':min(counts) if counts else None,
        'maximum_characters_per_page':max(counts) if counts else None,
        'limitations':['密度来自PDF可抽取字符，包含标题页码，受数学字体和排版影响。', '统计差异不是教学质量、数学正确性或视觉验收结论。']}


def pedagogical_metrics(section: dict, spec: dict | None = None) -> dict:
    """Expose requests and rendering risks separately from actual mathematical results."""
    units=section.get('units',[])
    by_id={u['id']:u for u in units}
    kinds={u['kind'] for u in units}
    wrappers=[]; exercise_links=[]; orphan_solutions=[]
    for unit in units:
        if unit['kind'] in ('definition','theorem','proof','example','exercise','solution'):
            pattern=r'\\begin\s*\{'+re.escape(unit['kind'])+r'\}'
            if re.search(pattern,unit.get('tex','')):
                wrappers.append({'unit_id':unit['id'],'kind':unit['kind'],'environment':unit['kind']})
        if unit['kind']=='solution':
            target=by_id.get(unit.get('relates_to'),{})
            if target.get('kind')=='exercise':
                exercise_links.append({'exercise':target['id'],'solution':unit['id']})
            elif target.get('kind')!='example':
                orphan_solutions.append(unit['id'])
    calculations=section.get('calculations',[])
    return {'section_id':section.get('section_id'),'status':'DESCRIPTIVE_NEEDS_REVIEW',
        'mathematical_correctness':'NOT_ASSESSED',
        'missing_planned_kinds':sorted(set((spec or {}).get('required_kinds',[]))-kinds),
        'render_wrapper_candidates':wrappers,'exercise_solution_links':exercise_links,
        'unresolved_solution_relation_unit_ids':orphan_solutions,
        'structured_calculations':{'status':'REQUESTED_NOT_VERIFIED' if calculations else 'NOT_RUN',
            'count':len(calculations),'requested_unit_ids':sorted({c['unit_id'] for c in calculations if isinstance(c,dict) and isinstance(c.get('unit_id'),str)}),
            'requested_kinds':dict(Counter(c.get('kind','unspecified') for c in calculations if isinstance(c,dict))),
            'missing_explicit_assumptions':[c.get('id',f'C{i+1}') for i,c in enumerate(calculations) if isinstance(c,dict) and not isinstance(c.get('assumptions'),dict)]},
        'limitations':['只统计已发出的计算请求；是否通过须读同一候选的实际math证据，不能将请求计数当核算结果。',
            '外层环境候选须结合实际渲染器及修复后TeX复核；初稿风险不等于最终产物缺陷。',
            '练习答案关联不证明已放到指定位置；须复核最终TeX与实际PDF。']}


def request_metrics(events: list[dict], actual_request_count: int, limit: int) -> dict:
    records = []
    current = None
    for event in events:
        data = event.get('payload') or json.loads(event.get('payload_json', '{}'))
        if event['type'] == 'provider.request':
            current = {'sequence':event['sequence'], 'timestamp':event.get('timestamp'),
                **{k:data.get(k) for k in ('role','model','attempt','input_hash')},
                'status':'NO_FINAL_RESPONSE_RECORDED', 'elapsed_seconds':None, 'usage':None, 'billing_uncertain':True,
                'streaming':data.get('streaming',False)}
            records.append(current)
        elif event['type'] == 'provider.result' and current and data.get('role') == current['role']:
            for key in ('http_status','elapsed_seconds','usage','request_id','response_id','billing_uncertain'):
                if key in data:
                    current[key] = data[key]
            if 'elapsed_seconds' in data and 'http_status' not in data:
                current['elapsed_basis']='provider_complete_request'
            if data.get('stream_complete') or data.get('usage') is not None or data.get('output_hash') or data.get('status'):
                try:
                    elapsed=(datetime.fromisoformat(event['timestamp'])-datetime.fromisoformat(current['timestamp'])).total_seconds()
                    current['observed_response_wall_seconds']=round(max(0,elapsed),3)
                except (ValueError,TypeError,KeyError):
                    pass
            if data.get('http_status') is not None:
                current['status'] = 'HTTP_' + str(data['http_status'])
            if data.get('usage') is not None:
                current['billing_uncertain'] = False
            if data.get('status'):
                current['status'] = data['status']
            if data.get('validation_errors'):
                current['schema_errors'] = data['validation_errors']
                current['status'] = 'SCHEMA_INVALID'
            if data.get('output_hash'):
                current['status'] = 'SCHEMA_VALIDATED'
    for record in records:
        # The first SSE iteration recorded only headers latency. Keep that value
        # as evidence and derive a labelled wall measurement from durable events.
        if record.get('streaming') and record.get('elapsed_basis')!='provider_complete_request' and record.get('observed_response_wall_seconds') is not None:
            record['original_reported_elapsed_seconds']=record['elapsed_seconds']
            record['elapsed_seconds']=record['observed_response_wall_seconds']
            record['elapsed_basis']='durable_event_wall_time_including_local_validation'
    usage_records = [r['usage'] for r in records if isinstance(r.get('usage'),dict)]
    token_fields=('prompt_tokens','completion_tokens','total_tokens')
    known = {k:(sum(u[k] for u in usage_records if type(u.get(k)) is int) if any(type(u.get(k)) is int for u in usage_records) else None) for k in token_fields}
    return {'request_count':actual_request_count, 'recorded_requests':len(records), 'request_limit':limit,
        'remaining_requests':max(0,limit-actual_request_count), 'requests':records,
        'known_usage_sum':known if usage_records else None,
        'usage_reporting_complete':len(usage_records)==actual_request_count and all(all(type(u.get(k)) is int for k in token_fields) for u in usage_records),
        'known_elapsed_seconds':round(sum(r['elapsed_seconds'] for r in records if isinstance(r.get('elapsed_seconds'),(int,float))),3),
        'price':None, 'price_status':'NOT_PROVIDED',
        'limitations':['供应商未报告的token/费用不推算为零。', '崩溃或超时可能已经计费；请求计数在发送前持久化。']}


def comparison(reference: dict, generated: dict, quality: dict | None, decision_coverage: dict | None) -> dict:
    quality = quality or {}
    ref_counts = reference['units']['normalized_kind_counts']
    gen_counts = generated['units']['normalized_kind_counts']
    types = sorted(set(ref_counts) | set(gen_counts))
    statuses = {k:quality.get(k, {}).get('status','NOT_RUN') for k in ('content','math','compile','layout','policy','security')}
    decision_statuses = Counter(d.get('status','NOT_RUN') for d in (decision_coverage or {}).get('decisions', []))
    return {'status':'NEEDS_REVIEW', 'semantic_equivalence':'NOT_ASSESSED', 'teacher_visual_review':'NOT_RUN',
        'automated_quality_statuses':statuses, 'decision_status_counts':dict(decision_statuses),
        'unit_type_differences':[{'kind':k,'reference':ref_counts.get(k,0),'generated':gen_counts.get(k,0),'delta':gen_counts.get(k,0)-ref_counts.get(k,0)} for k in types],
        'pages':{'reference':reference['pdf'].get('page_count'),'generated':generated['pdf'].get('page_count')},
        'density':{'reference':reference['pdf'].get('mean_characters_per_page'),'generated':generated['pdf'].get('mean_characters_per_page')},
        'required_review':['教师逐项复核定理前提、量词、定义域、先修闭合与练习难度。','按页面图像及其哈希复核公式裁切、遮挡和正文密度。','检查真实选择落实；统计与原文差异不能单独判定数学错误。'],
        'limitations':['非文本相似度评分；不同表述或章节组织不会被自动判错。','即使所有自动维度PASS，本比较仍为NEEDS_REVIEW。']}


class BenchmarkRunner:
    """Use exactly the public application orchestration; never submit a page review."""
    def __init__(self, settings, run_dir: Path, *, per_run_budget=60, total_budget=240):
        from .service import Service
        self.settings = settings
        self.run_dir = Path(run_dir).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.run_dir / 'benchmark_state.json'
        self.state = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {
            'schema_version':1, 'created_at':datetime.now(timezone.utc).isoformat(), 'workspace':str(settings.workspace),
            'actor':'benchmark_driver', 'teacher_visual_review':'NOT_RUN', 'cases':{}, 'per_run_budget':per_run_budget, 'total_budget':total_budget}
        if Path(self.state['workspace']).resolve() != settings.workspace:
            raise ValueError('Resume workspace does not match persisted benchmark')
        if self.state['per_run_budget'] != per_run_budget or self.state['total_budget'] != total_budget:
            raise ValueError('Resume budgets must match the original benchmark manifest')
        self.per_run_budget, self.total_budget = per_run_budget, total_budget
        self.service = Service(settings, actor='benchmark_driver')
        self.save()

    def save(self):
        self.state['updated_at'] = datetime.now(timezone.utc).isoformat()
        write_json(self.state_path, self.state)

    def all_requests(self):
        return sum(self.service.store.get_run(v['run_id'])['request_count'] for v in self.state['cases'].values() if v.get('run_id'))

    def snapshot(self, name):
        item = self.state['cases'][name]
        run = self.service.store.get_run(item['run_id'])
        with self.service.store.connect() as c:
            events = [dict(r) for r in c.execute('SELECT * FROM events WHERE run_id=? ORDER BY sequence', (run['id'],))]
        item.update(status=run['status'], stage=run['stage'], request_count=run['request_count'], error=run['error'],
            plan_revision=run['active_plan_revision'], plan_hash=(run.get('plan') or {}).get('hash'),
            elapsed_wall_seconds=round(time.time()-item['started_epoch'],3))
        item['request_metrics'] = request_metrics(events, run['request_count'], item.get('effective_request_limit',self.per_run_budget))
        write_json(self.run_dir / name / 'run_snapshot.json', run)
        write_json(self.run_dir / name / 'request_metrics.json', item['request_metrics'])
        self.save()
        return run

    def tick(self, name):
        from .worker import Worker
        item = self.state['cases'][name]
        with self.service.store.connect() as c:
            waiting=c.execute("SELECT run_id FROM jobs WHERE status IN ('queued','running')").fetchall()
        if any(row['run_id'] != item['run_id'] for row in waiting):
            raise AgentError('WORKSPACE_NOT_EXCLUSIVE','Benchmark worker refuses unrelated queued jobs; use its dedicated workspace.')
        already = self.service.store.get_run(item['run_id'])['request_count']
        available = self.total_budget - self.all_requests()
        limit = min(self.per_run_budget, already + available)
        if limit <= already:
            item['driver_stop'] = 'TOTAL_REQUEST_BUDGET_EXHAUSTED'
            self.save()
            return False
        item['effective_request_limit'] = limit
        local_settings = self.settings.model_copy(update={'max_requests_per_run':limit})
        self.save()
        errors = []
        def work():
            try:
                Worker(local_settings).tick()
            except BaseException as exc:
                errors.append(exc)
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        while thread.is_alive():
            thread.join(timeout=2)
            self.snapshot(name)
        self.snapshot(name)
        if errors:
            raise errors[0]
        return True

    def preserve_attempt(self, name, run, reason):
        """Immutable snapshots around retries keep the first failure reviewable."""
        attempt=max((job['attempt'] for job in run['jobs']),default=0)
        target=self.run_dir/name/'attempts'/f"attempt-{attempt}-{reason}-{time.time_ns()}"
        target.mkdir(parents=True,exist_ok=False)
        files=[]
        for source in [self.state_path,self.run_dir/'driver_failure.json']+[self.run_dir/name/file for file in ('run_snapshot.json','request_metrics.json','comparison.json','comparison.md')]:
            if source.is_file():
                destination=target/source.name
                shutil.copyfile(source,destination)
                files.append({'name':source.name,'sha256':digest(destination.read_bytes())})
        write_json(target/'attempt_manifest.json',{'run_id':run['id'],'status':run['status'],'reason':reason,
            'request_count':run['request_count'],'jobs':run['jobs'],'error':run['error'],'files':files,'teacher_visual_review':'NOT_RUN'})
        self.state['cases'][name].setdefault('attempt_archives',[]).append(str(target))
        self.save()
        return target

    def execute_case(self, name: str, *, retry_failed=False):
        from .domain import NewRun, DecisionsRequest, Selection, ConfirmRequest, ExecuteRequest
        case = CASES[name]
        if name not in self.state['cases']:
            run = self.service.create(NewRun(workflow_id='lecture.generate', topic=case['topic'], provider='live', trusted_input=True))
            self.state['cases'][name] = {'run_id':run['id'], 'started_epoch':time.time(), 'dataset':case['dataset'], 'topic':case['topic'], 'teacher_visual_review':'NOT_RUN'}
            self.save()
        run = self.snapshot(name)
        if run['input']['provider'] != 'live':
            raise ValueError('Benchmark cannot substitute mock for live')
        if run['status'] in ('FAILED','BLOCKED'):
            if not retry_failed:
                return run
            self.preserve_attempt(name,run,'before-retry')
            self.service.retry(run['id'])
            run = self.snapshot(name)
        if run['status'] == 'CREATED':
            self.service.propose(run['id'])
            run = self.snapshot(name)
        if run['status'] in ('QUEUED','PLANNING','BUILDING','LOCAL_REVIEW','GLOBAL_REVIEW','REPAIRING'):
            # Worker reclaims expired leases; never force-fence another active worker.
            if any(j['status']=='running' for j in run['jobs']):
                with self.service.store.connect() as c:
                    live = c.execute("SELECT 1 FROM jobs WHERE run_id=? AND status='running' AND lease_deadline>?", (run['id'],time.time())).fetchone()
                if live:
                    self.state['cases'][name]['driver_stop']='ACTIVE_LEASE_WAIT_BEFORE_RESUME'
                    self.save()
                    return run
            self.tick(name)
            run = self.snapshot(name)
        if run['status'] in ('AWAITING_PLAN_INPUT','PLAN_READY'):
            plan = run['plan']
            if not case['min_sections'] <= len(plan['sections']) <= case['max_sections']:
                self.state['cases'][name]['driver_stop']='PLAN_SCOPE_NEEDS_REVIEW'
                self.save()
                return run
            selections = []
            for question in plan['questions']:
                if question.get('selected_option_ids'):
                    continue
                wanted = CHOICES.get(question['id'])
                if wanted is None or wanted not in {o['id'] for o in question['options']}:
                    self.state['cases'][name]['driver_stop']='UNKNOWN_QUESTION_NEEDS_REVIEW'
                    self.save()
                    return run
                selections.append(Selection(question_id=question['id'], question_revision=question['revision'], selected_option_ids=[wanted]))
            if selections:
                self.service.decisions(run['id'], DecisionsRequest(expected_plan_revision=plan['revision'], decisions=selections))
                run = self.snapshot(name)
            plan = run['plan']
            self.service.confirm(run['id'], ConfirmRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], action_id='benchmark_driver:'+name+':'+plan['hash'][:16]))
            run = self.snapshot(name)
        if run['status']=='PLAN_CONFIRMED':
            plan=run['plan']
            self.service.execute(run['id'],ExecuteRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],idempotency_key='benchmark_driver:'+name+':'+plan['hash'][:16]))
            self.tick(name)
            run=self.snapshot(name)
        # AWAITING_USER_REVIEW is the end of automation. Never call review/publish.
        return run

    def reference_metrics(self, name):
        from .parsing import load_project
        from .pdfcheck import inspect_pdf
        case=CASES[name]
        cache=self.run_dir/'references'/case['dataset']/'metrics.json'
        tex=self.settings.reference_root/case['directory']/'大学数学（一）(1).tex'
        pdf=tex.with_suffix('.pdf')
        hashes={'tex':digest(tex.read_bytes()),'pdf':digest(pdf.read_bytes())}
        if cache.exists():
            old=json.loads(cache.read_text(encoding='utf-8'))
            if old.get('source_hashes')==hashes:
                return old
        parsed=load_project(tex.parent,tex.name)
        inspection=inspect_pdf(pdf,cache.parent/'pages',beamer=False)
        write_json(cache.parent/'pdf_inspection.json',inspection)
        result={'dataset':case['dataset'],'source_tex':str(tex),'source_pdf':str(pdf),'source_hashes':hashes,
            'units':unit_metrics(parsed['units'],parsed['sections']), 'pdf':page_metrics(inspection),
            'parser_issues':parsed.get('issues',[]),'teacher_visual_review':'NOT_RUN',
            'reference_use':'Local metrics only; API context is bounded application retrieval, never this entire chapter'}
        write_json(cache,result)
        return result

    def analyze(self, name):
        run=self.snapshot(name)
        with self.service.store.connect() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM artifacts WHERE run_id=? AND revision=? ORDER BY created_at', (run['id'],run['active_plan_revision'] or 0))]
            step_rows=c.execute("SELECT step_key,output_json FROM steps WHERE run_id=? AND step_key LIKE 'section.%' ORDER BY created_at", (run['id'],)).fetchall()
        verified=[]; documents={}
        for row in rows:
            path=within(self.settings.workspace,row['storage_key'])
            valid=path.is_file() and digest(path.read_bytes())==row['sha256']
            verified.append({'artifact_id':row['artifact_id'],'name':row['name'],'path':str(path),'sha256':row['sha256'],'hash_check':'PASS' if valid else 'FAIL'})
            if valid and row['name'] in ('quality_report.json','decision_coverage.json','pdf_inspection.json'):
                documents[row['name']]=json.loads(path.read_text(encoding='utf-8'))
        sections={key:json.loads(value) for key,value in step_rows}
        units=[u for step in sections.values() for u in step['generated']['units']]
        plan=run.get('plan') or {}
        build_root=self.settings.workspace/'b'/run['id'][:16]
        partial_checks=[]
        for path in sorted(build_root.glob('s*/*.json')):
            if path.name=='compile.json' or path.name.startswith('review-'):
                data=json.loads(path.read_text(encoding='utf-8'))
                partial_checks.append({'path':str(path),'sha256':digest(path.read_bytes()),
                    'section_id':data.get('section_id'), 'compile_status':data.get('status') if path.name=='compile.json' else None,
                    'math_status':data.get('math',{}).get('status'),
                    'issue_severities':dict(Counter(i.get('severity','unknown') for i in data.get('issues',[])))})
        by_section_id={s['id']:s for s in plan.get('sections',[])}
        candidate_paths=list(build_root.glob('s*/candidate.json'))
        draft_diagnostics=[]
        for path in candidate_paths:
            draft=json.loads(path.read_text(encoding='utf-8'))
            draft_diagnostics.append({'path':str(path),'sha256':digest(path.read_bytes()),'initial_candidate_only':True,
                'diagnostics':pedagogical_metrics(draft,by_section_id.get(draft.get('section_id')))})
        generated={'units':unit_metrics(units,plan.get('sections',[]),plan.get('prerequisites',[])),
            'pdf':page_metrics(documents.get('pdf_inspection.json')),'checked_section_count':len(sections),
            'planned_section_count':len(plan.get('sections',[])), 'completed_body_only':True,
            'exercise_choices':plan.get('lecture',{}),
            'partial_candidate_paths':[str(p) for p in candidate_paths],
            'draft_candidate_diagnostics':draft_diagnostics,
            'checked_section_pedagogy':[pedagogical_metrics(step['generated'],by_section_id.get(step['generated'].get('section_id'))) for step in sections.values()],
            'partial_check_evidence':partial_checks,
            'plan_reference_context':plan.get('reference_context'), 'artifacts':verified}
        reference=self.reference_metrics(name)
        result={'case':name,'dataset':CASES[name]['dataset'],'run_id':run['id'],'run_status':run['status'],
            'request_metrics':self.state['cases'][name]['request_metrics'],'elapsed_wall_seconds':self.state['cases'][name]['elapsed_wall_seconds'],
            'reference':reference,'generated':generated,
            'comparison':comparison(reference,generated,documents.get('quality_report.json'),documents.get('decision_coverage.json')),
            'error':run['error'],'driver_stop':self.state['cases'][name].get('driver_stop'),
            'recovery':'Use the same --run-dir and --retry-failed only after correcting the recorded failure; never recreate the run silently.'}
        write_json(self.run_dir/name/'comparison.json',result)
        lines=[f'# {name} 真实 API 基准比较', '', f"运行状态：{run['status']}；比较结论：**NEEDS_REVIEW**；教师人工验收：**NOT_RUN**。",
            '',f"实际请求 {result['request_metrics']['request_count']}；已确认正文 {len(sections)}/{len(plan.get('sections',[]))} 节；已用墙钟 {result['elapsed_wall_seconds']} 秒。",
            '费用未由供应商提供；缺失 token 不视为零。原件只在本地统计；模型采用应用现有的有界样例检索。', '',
            '| 单元类型 | 原讲义 | 生成讲义已检查部分 |','|---|---:|---:|']
        lines += [f"| {d['kind']} | {d['reference']} | {d['generated']} |" for d in result['comparison']['unit_type_differences']]
        lines += ['',f"原件页数：{reference['pdf'].get('page_count')}；生成页数：{generated['pdf'].get('page_count')}。",
            f"实际自动维度：{json.dumps(result['comparison']['automated_quality_statuses'],ensure_ascii=False)}。",
            f"真实选择落实：{json.dumps(result['comparison']['decision_status_counts'],ensure_ascii=False)}。",'',
            '类型、页数、密度及条件词仅作描述；与原文不同不自动判错，统计不升级为数学证明或教学验收。',
            '详见 comparison.json 的逐页密度、先修字段、条件词证据、练习关联、每次请求／耗时／预算、错误和带哈希产物。',
            f"失败记录：{scrub(run['error']) if run['error'] else '无已记录运行错误'}。"]
        (self.run_dir/name/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        if run['status'] in ('FAILED','BLOCKED','AWAITING_USER_REVIEW'):
            self.preserve_attempt(name,run,'result')
        return result

    def run(self, phase='smoke', *, execute_live=False, retry_failed=False):
        names=['smoke'] if phase=='smoke' else ['CH01','CH02','CH03'] if phase=='chapters' else list(CASES)
        if execute_live and (not self.settings.live_api_enabled or not self.settings.api_key.get_secret_value()):
            raise AgentError('PROVIDER_NOT_CONFIGURED','Benchmark requires enabled live API and environment key; no mock fallback.')
        results=[]
        for name in names:
            if execute_live:
                if name!='smoke':
                    smoke=self.state['cases'].get('smoke',{})
                    if not smoke.get('run_id') or self.service.store.get_run(smoke['run_id'])['status']!='AWAITING_USER_REVIEW':
                        raise AgentError('SMOKE_NOT_READY','Complete the two-section smoke to AWAITING_USER_REVIEW before full chapters.')
                self.execute_case(name,retry_failed=retry_failed)
            if name in self.state['cases']:
                results.append(self.analyze(name))
            else:
                self.reference_metrics(name)
        summary={'status':'NEEDS_REVIEW' if results else 'LIVE_NOT_RUN', 'teacher_visual_review':'NOT_RUN',
            'cases':[{'case':r['case'],'run_id':r['run_id'],'status':r['run_status'],'report':str(self.run_dir/r['case']/'comparison.json')} for r in results],
            'total_requests':self.all_requests(),'total_budget':self.total_budget,'live_executed_this_invocation':execute_live}
        write_json(self.run_dir/'summary.json',summary)
        return summary
