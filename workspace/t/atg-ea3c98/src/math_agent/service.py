import copy
import json
import mimetypes
import shutil
import time
from pathlib import Path
from .domain import NewRun, ConfirmRequest, ExecuteRequest, RecheckRequest, DecisionsRequest, ReviewRequest, RevisePlanRequest
from .settings import Settings
from .store import Store
from .util import AgentError, canonical, digest, now, uid, within, write_json


class Service:
    def __init__(self, settings: Settings, actor='local_user'):
        if actor not in ('local_user','benchmark_driver'):
            raise ValueError('Unsupported internal actor')
        self.actor=actor
        self.settings = settings
        self.store = Store(settings.db_path)

    def create(self, data: NewRun):
        if data.workflow_id == 'lecture.generate' and not data.topic.strip():
            raise AgentError('TOPIC_REQUIRED', '请输入专题')
        rid = uid()
        payload = data.model_dump()
        payload.update(schema_version=1, units=[], attachments=[])
        with self.store.transaction() as c:
            c.execute('INSERT INTO runs(id,workflow_id,status,stage,input_json,input_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                      (rid, data.workflow_id, 'CREATED', 'input', canonical(payload), digest(payload), now(), now()))
            self.store.event(c, rid, 'run.created', {'provider': data.provider, 'model_id': data.model_id, 'workflow_id': data.workflow_id,'actor':self.actor})
        return self.store.get_run(rid)

    def list_runs(self):
        with self.store.connect() as c:
            rows = c.execute('SELECT id,workflow_id,status,stage,input_json,created_at,updated_at FROM runs ORDER BY created_at DESC LIMIT 200').fetchall()
        return [{**dict(r), 'input': json.loads(r['input_json'])} for r in rows]

    def get_budget(self, run_id):
        from .budget import defaults_from_settings
        return self.store.effective_budget(run_id, defaults_from_settings(self.settings))

    def get(self, run_id):
        run = self.store.get_run(run_id)
        from .model_evidence import routing_summary
        run['model_routing'] = routing_summary(self.store, run)
        run['budget'] = self.get_budget(run_id)
        run['budget']['can_increase'] = self.actor == 'local_user' and run['status'] == 'BLOCKED' and not any(
            job['status'] in ('queued', 'running') for job in run['jobs'])
        if run['status'] in ('BLOCKED', 'FAILED'):
            run['partial_checkpoints'] = self.partial_checkpoints(run_id)
        return run

    def increase_budget(self, run_id, request):
        from .budget import defaults_from_settings, increase
        return increase(self.store, run_id, request, defaults_from_settings(self.settings), self.actor)

    def import_legacy_request_budget(self, run_id, state_path, expected_sha256):
        from .budget import import_legacy_requests
        return import_legacy_requests(self.store, run_id, state_path, expected_sha256,
            self.settings.workspace, actor=self.actor)

    def partial_checkpoints(self, run_id):
        from .partial_delivery import checkpoint_items
        return checkpoint_items(self.store, self.settings.workspace, run_id)

    def partial_download(self, run_id, token):
        from .partial_delivery import download_checkpoint
        return download_checkpoint(self.store, self.settings.workspace, run_id, token)

    def attachments(self, run_id, name, data, main_file=None):
        from .parsing import safe_extract_zip, load_project, parse_tex
        if len(data) > 50 * 1024 * 1024:
            raise AgentError('UPLOAD_TOO_LARGE', '文件超过 50 MiB', 413)
        if Path(name).name != name or len(name)>200 or any(ord(ch)<32 or ch in '/\\:<>"|?*' for ch in name):
            raise AgentError('BAD_FILENAME', '文件名包含路径或控制字符')
        if Path(name).suffix.lower() not in ('.tex', '.zip'):
            raise AgentError('UNSUPPORTED_UPLOAD', '只接受 TeX 或包含依赖的 ZIP')
        run = self.store.get_run(run_id)
        if run['status'] not in ('CREATED', 'BLOCKED', 'FAILED') or run['approval'] or run['active_plan_revision'] is not None:
            raise AgentError('INPUT_LOCKED', '输入已进入规划或审批；请新建任务以替换原件', 409)
        root = self.settings.workspace / 'inputs' / run_id / uid()
        root.mkdir(parents=True, exist_ok=False)
        original_upload=root.parent/(root.name+'.upload')
        original_upload.write_bytes(data)
        original_root=root
        enrichment=None
        try:
            if name.lower().endswith('.zip'):
                members = safe_extract_zip(data, root)
                candidates = []
                for candidate in root.rglob('*.tex'):
                    try:
                        content = candidate.read_text(encoding='utf-8-sig')
                    except UnicodeError:
                        content = candidate.read_text(encoding='gb18030')
                    if '\\documentclass' in content:
                        candidates.append(candidate.relative_to(root).as_posix())
                if main_file:
                    entry = within(root, main_file).relative_to(root).as_posix()
                elif len(candidates) == 1:
                    entry = candidates[0]
                else:
                    raise AgentError('MAIN_FILE_AMBIGUOUS', 'ZIP 需唯一主 TeX，或明确指定 main_file；候选：' + ', '.join(candidates))
            else:
                (root / name).write_bytes(data)
                entry = name
            parsed = load_project(root, entry)
            if run['input'].get('use_reference_bibliography'):
                from .manuscript import complete_bibliography
                from .parsing import decode_tex
                manuscript=self.settings.reference_root/'大学数学（一）(1).tex'
                if not manuscript.is_file():
                    raise ValueError('所选本地全稿不存在，不能补造书目。请取消补齐选项或提供全稿。')
                manuscript_bytes=manuscript.read_bytes()
                manuscript_text,_=decode_tex(manuscript_bytes)
                enriched=complete_bibliography(parsed['expanded_tex'],manuscript_text,
                    source_name=entry,manuscript_name=manuscript.name)
                enrichment={k:v for k,v in enriched.items() if k!='text'}
                enrichment.update(original_upload_sha256=digest(data),manuscript_bytes_sha256=digest(manuscript_bytes),
                                  authorization='explicit_input_option_pending_plan_confirmation')
                if enriched.get('conflicting_keys'):
                    raise ValueError('引用书目存在冲突，须核对来源后再上传：'+','.join(enriched['conflicting_keys']))
                if enriched.get('added_keys'):
                    prepared=within(self.settings.workspace,original_root.relative_to(self.settings.workspace).as_posix()+'-prepared')
                    shutil.copytree(original_root,prepared)
                    root=prepared
                    # The expanded source already preserves original CRLF/LF.
                    # Windows text translation would turn CRLF into CRCRLF,
                    # inserting TeX paragraph breaks inside macro arguments.
                    (root/entry).write_bytes(enriched['text'].encode('utf-8'))
                    parsed=load_project(root,entry)
        except ValueError as exc:
            raise AgentError('INPUT_INVALID', str(exc)) from None
        if not parsed.get('units'):
            raise AgentError('EMPTY_SOURCE', '未找到讲义正文单元')
        payload = {**run['input'], 'source_key': root.relative_to(self.settings.workspace).as_posix(),
                   'original_source_key':original_root.relative_to(self.settings.workspace).as_posix(),
                   'original_upload_key':original_upload.relative_to(self.settings.workspace).as_posix(),
                   'source_enrichment':enrichment,
                   'main_file': entry, 'filename': name, 'upload_hash': digest(data),
                   'units': parsed['units'], 'parsed': parsed,
                   'attachments': [{'path': p.relative_to(root).as_posix(), 'sha256': digest(p.read_bytes()), 'size': p.stat().st_size} for p in root.rglob('*') if p.is_file()]}
        with self.store.transaction() as c:
            current = self.store.row(c, run_id)
            if current['active_plan_revision'] != run['active_plan_revision'] or current['status'] not in ('CREATED', 'BLOCKED', 'FAILED'):
                raise AgentError('CONFLICT', '输入状态已改变', 409)
            c.execute('UPDATE runs SET input_json=?,input_hash=?,status=?,stage=?,updated_at=? WHERE id=?',
                      (canonical(payload), digest(payload), 'CREATED', 'input.validated', now(), run_id))
            self.store.event(c, run_id, 'input.snapshot', {'hash': digest(data), 'files': len(payload['attachments'])})
        return self.store.get_run(run_id)

    def propose(self, run_id):
        with self.store.transaction() as c:
            run = self.store.row(c, run_id)
            if run['active_plan_revision'] is not None:
                raise AgentError('PLAN_EXISTS', '计划已存在；请修改选择或新建任务', 409)
            payload = json.loads(run['input_json'])
            if run['workflow_id'] == 'beamer.from_tex' and not payload.get('units'):
                raise AgentError('SOURCE_REQUIRED', '请先上传讲义 TeX/ZIP')
            key = digest([run_id, 'plan', run['input_hash']])
            return self._enqueue(c, run, 'plan', key)

    def _enqueue(self, c, run, kind, key):
        row = c.execute('SELECT * FROM jobs WHERE build_key=?', (key,)).fetchone()
        if row:
            return dict(row)
        jid = uid()
        c.execute('INSERT INTO jobs(id,run_id,kind,build_key,status,created_at) VALUES(?,?,?,?,?,?)',
                  (jid, run['id'], kind, key, 'queued', now()))
        c.execute('UPDATE runs SET status=?,stage=?,error_json=NULL,updated_at=? WHERE id=?',
                  ('QUEUED', kind + '.queued', now(), run['id']))
        self.store.event(c, run['id'], 'job.queued', {'job_id': jid, 'kind': kind})
        return dict(c.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone())

    def decisions(self, run_id, request: DecisionsRequest):
        with self.store.transaction() as c:
            run = self.store.row(c, run_id)
            plan = self.store.current_plan(c, run)
            if not plan or plan['revision'] != request.expected_plan_revision:
                raise AgentError('REVISION_CONFLICT', '问题版本已更新，请刷新后再提交', 409)
            if run['status'] not in ('AWAITING_PLAN_INPUT', 'PLAN_READY', 'PLAN_CONFIRMED'):
                raise AgentError('PLAN_IN_USE', '任务正在构建或已生成；请新建任务修改内容计划', 409)
            old = copy.deepcopy(plan)
            plan.setdefault('decisions', [])
            plan.setdefault('decision_ids', [])
            for selection in request.decisions:
                q = next((q for q in plan['questions'] if q['id'] == selection.question_id), None)
                if not q or q['revision'] != selection.question_revision:
                    raise AgentError('QUESTION_CONFLICT', '问题不存在或版本过期', 409)
                valid = {o['id']: o for o in q['options']}
                ids = selection.selected_option_ids
                if not ids or len(set(ids)) != len(ids) or any(i not in valid for i in ids) or (q['selection_mode'] == 'single' and len(ids) != 1):
                    raise AgentError('INVALID_OPTION', '无效选项或选择数量')
                if 'CUSTOM' in ids:
                    text = selection.custom_input.strip()
                    if not text:
                        raise AgentError('CUSTOM_REQUIRED', '自定义选项需要输入内容')
                    if any(x in text.lower() for x in ('scriptsize', '\\tiny', '\\fontsize', 'shrink', '\\resizebox', '\\scalebox')):
                        raise AgentError('RULE_CONFLICT', '自定义输入与四档字号等硬约束冲突')
                    effect = {'custom': text}
                else:
                    effect = valid[ids[0]].get('effects', {'value': ids[0]})
                for field in q['affected_fields']:
                    parts = field.split('.')
                    target = plan
                    for part in parts[:-1]:
                        target = target.setdefault(part, {})
                    target[parts[-1]] = effect.get('value', effect)
                section_requirement_changes = []
                if run['workflow_id'] == 'lecture.generate' and 'lecture.exercises' in q['affected_fields']:
                    exercise_policy = plan.get('lecture', {}).get('exercises')
                    # Derived requirements are part of this same versioned decision.
                    # Leave natural-language custom policies for explicit review.
                    if exercise_policy in ('none', 'with_answers'):
                        for section in plan['sections']:
                            before_kinds = list(section.get('required_kinds', []))
                            after_kinds = list(before_kinds)
                            if exercise_policy == 'none':
                                after_kinds = [kind for kind in after_kinds if kind != 'exercise']
                                # An example must keep its solution. A solution
                                # required solely with exercises is removed with them.
                                if 'exercise' in before_kinds and 'example' not in before_kinds:
                                    after_kinds = [kind for kind in after_kinds if kind != 'solution']
                            else:
                                for kind in ('exercise', 'solution'):
                                    if kind not in after_kinds:
                                        after_kinds.append(kind)
                            if after_kinds != before_kinds:
                                section['required_kinds'] = after_kinds
                                section_requirement_changes.append({'section_id':section['id'],
                                    'before':before_kinds,'after':after_kinds})
                did = uid()
                decision = {'id': did, **selection.model_dump(), 'resolved_effects': effect, 'affected_fields': q['affected_fields'], 'actor': self.actor, 'timestamp': now()}
                if section_requirement_changes:
                    decision['derived_section_requirements'] = section_requirement_changes
                c.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?)', (did, run_id, q['id'], q['revision'], canonical(decision), self.actor, now()))
                plan['decisions'] = [d for d in plan['decisions'] if d.get('question_id') != q['id']] + [decision]
                plan['decision_ids'] = [d['id'] for d in plan['decisions']]
                q['selected_option_ids'] = ids
                q['custom_input'] = selection.custom_input
            if request.omitted_unit_ids is not None:
                units = {u['id']: u for u in json.loads(run['input_json']).get('units', [])}
                requested = set(request.omitted_unit_ids)
                if not requested.issubset(units):
                    raise AgentError('UNKNOWN_UNIT', '删除目标不唯一或单元不存在，请从源清单选择')
                expanded = set(requested)
                for unit in units.values():
                    rel = unit.get('semantic_relations', {})
                    if isinstance(rel, list):
                        linked = [r.get('target') or r.get('target_id') for r in rel if r.get('type') in ('solution_of', 'proof_of')]
                    else:
                        linked = [rel.get('solution_of'), rel.get('proof_of')]
                    if any(target in requested for target in linked):
                        expanded.add(unit['id'])
                # Deleting referenced definitions cannot silently remove downstream units.
                retained = [u for u in units.values() if u['id'] not in expanded]
                impacted = [u['id'] for u in retained if set(u.get('dependencies', [])) & expanded]
                if impacted:
                    raise AgentError('DEPENDENCY_IMPACT', '删除会影响以下保留单元，请明确调整范围：' + ','.join(impacted))
                did = uid()
                omission_decision = {'id': did, 'type': 'omissions', 'requested': sorted(requested), 'resolved': sorted(expanded), 'actor': self.actor, 'timestamp': now()}
                c.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?)', (did, run_id, 'omissions', 1, canonical(omission_decision), self.actor, now()))
                plan['omissions'] = [{'unit_id': i, 'category': 'user_authorized_omission', 'decision_id': did} for i in sorted(expanded)]
                plan['decisions'] = [d for d in plan['decisions'] if d.get('type') != 'omissions'] + [omission_decision]
            if request.additions is not None:
                sections = {s['id'] for s in plan['sections']}
                additions = []
                for addition in request.additions:
                    if addition.insertion_location not in sections:
                        raise AgentError('INVALID_LOCATION', '新增内容必须指定实际 section ID')
                    from .parsing import preflight_tex
                    if preflight_tex(addition.new_content):
                        raise AgentError('UNSAFE_ADDITION', '新增 TeX 未通过预检')
                    additions.append({'id': uid(), **addition.model_dump(), 'actor': self.actor})
                did = uid()
                record = {'id': did, 'type': 'additions', 'resolved': additions, 'actor': self.actor, 'timestamp': now()}
                c.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?)', (did, run_id, 'additions', 1, canonical(record), self.actor, now()))
                plan['additions'] = [{**a, 'decision_id': did} for a in additions]
                plan['decisions'] = [d for d in plan['decisions'] if d.get('type') != 'additions'] + [record]
            plan['decision_ids'] = [d['id'] for d in plan['decisions']]
            plan['unresolved_blocking_questions'] = [q['id'] for q in plan['questions'] if q.get('blocking') and not q.get('selected_option_ids')]
            plan['diff'] = [{'field': k, 'before': old.get(k), 'after': plan.get(k)} for k in ('lecture', 'sections', 'theme', 'omissions', 'additions') if old.get(k) != plan.get(k)]
            return self.store.save_plan(c, run_id, plan)

    def _check_expected(self, c, run_id, revision, hash_):
        run = self.store.row(c, run_id)
        p = self.store.current_plan(c, run)
        if not p or p['revision'] != revision or p['hash'] != hash_:
            raise AgentError('REVISION_CONFLICT', '计划版本/哈希已更新，请刷新', 409)
        return run, p

    def revise(self, run_id, req: RevisePlanRequest):
        with self.store.transaction() as c:
            run=self.store.row(c,run_id)
            plan=self.store.current_plan(c,run)
            if not plan or plan['revision']!=req.expected_plan_revision:
                raise AgentError('REVISION_CONFLICT','计划版本过期，请刷新',409)
            if run['status'] not in ('AWAITING_PLAN_INPUT','PLAN_READY','PLAN_CONFIRMED'):
                raise AgentError('PLAN_IN_USE','构建期间不能修改内容计划',409)
            before=copy.deepcopy(plan)
            sections={s['id']:s for s in plan['sections']}
            if not set(req.section_titles).issubset(sections):
                raise AgentError('UNKNOWN_SECTION','章节 ID 不存在')
            if any(not title.strip() or len(title)>200 for title in req.section_titles.values()):
                raise AgentError('INVALID_TITLE','章节标题须为 1–200 个字符')
            for sid,title in req.section_titles.items(): sections[sid]['title']=title.strip()
            if req.title is not None:plan['title']=req.title.strip()
            if req.section_order is not None:
                if len(req.section_order)!=len(sections) or set(req.section_order)!=set(sections):
                    raise AgentError('INVALID_ORDER','章节顺序必须完整且不重复')
                seen=set()
                for sid in req.section_order:
                    if not set(sections[sid].get('prerequisites',[])).issubset(seen):
                        raise AgentError('DEPENDENCY_ORDER','章节顺序违反先修依赖')
                    seen.add(sid)
                if run['workflow_id']=='beamer.from_tex' and req.section_order!=[s['id'] for s in plan['sections']]:
                    raise AgentError('SOURCE_ORDER_REVIEW','源讲义重排的语义依赖尚未核验；请保留原顺序')
                plan['sections']=[sections[sid] for sid in req.section_order]
            did=uid()
            decision={'id':did,'type':'outline','resolved_effects':req.model_dump(exclude={'expected_plan_revision'}),'actor':self.actor,'timestamp':now()}
            c.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?)',(did,run_id,'outline',plan['revision'],canonical(decision),self.actor,now()))
            plan.setdefault('decisions',[]).append(decision)
            plan.setdefault('decision_ids',[]).append(did)
            plan['diff']=[{'field':field,'before':before.get(field),'after':plan.get(field)} for field in ('title','sections') if before.get(field)!=plan.get(field)]
            return self.store.save_plan(c,run_id,plan)

    def confirm(self, run_id, req: ConfirmRequest):
        with self.store.transaction() as c:
            run, p = self._check_expected(c, run_id, req.expected_plan_revision, req.expected_plan_hash)
            if p.get('unresolved_blocking_questions'):
                raise AgentError('UNANSWERED_QUESTIONS', '请完成必要选择后确认')
            if run['status'] not in ('PLAN_READY', 'PLAN_CONFIRMED'):
                raise AgentError('INVALID_STATE', '当前状态不能确认计划', 409)
            payload = json.loads(run['input_json'])
            if not payload.get('trusted_input'):
                raise AgentError('TRUST_REQUIRED', '原生编译不是隔离沙箱；请在新建任务时明确确认输入及模板可信')
            if p.get('theme') == 'fduclassroom':
                from .beamer import theme_status
                themes = theme_status(self.settings.reference_root)
                fdu = themes.get('fduclassroom', {})
                if not fdu.get('available', False):
                    raise AgentError('THEME_UNAVAILABLE', 'FDU 主题不完整：' + canonical(fdu))
                if p.get('theme_hash') != fdu.get('selected_sha256'):
                    raise AgentError('THEME_CHANGED','主题哈希已改变；请重新规划并确认主题',409)
            c.execute('INSERT OR IGNORE INTO approvals VALUES(?,?,?,?,?,?)', (run_id, p['revision'], p['hash'], run['input_hash'], req.action_id, now()))
            c.execute("UPDATE plans SET status='confirmed' WHERE run_id=? AND revision=?", (run_id, p['revision']))
            c.execute("UPDATE runs SET status='PLAN_CONFIRMED',stage='plan.confirmed',updated_at=? WHERE id=?", (now(), run_id))
            self.store.event(c, run_id, 'plan.confirmed', {'revision': p['revision'], 'hash': p['hash'], 'action_id': req.action_id,'actor':self.actor})
        return self.store.get_run(run_id)

    def execute(self, run_id, req: ExecuteRequest):
        with self.store.transaction() as c:
            run, p = self._check_expected(c, run_id, req.expected_plan_revision, req.expected_plan_hash)
            a = c.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?', (run_id, p['revision'])).fetchone()
            if not a or a['hash'] != p['hash'] or a['input_hash'] != run['input_hash']:
                raise AgentError('APPROVAL_REQUIRED', '请由用户确认当前计划')
            if run['status'] == 'CANCELLED':
                raise AgentError('CANCELLED', '已取消的任务不能执行，请新建任务', 409)
            key = digest([run_id, run['workflow_id'], 1, run['input_hash'], p['hash'], p.get('theme_hash'), 'rules-v1'])
            return self._enqueue(c, run, 'build', key)

    def recheck(self, run_id, req: RecheckRequest):
        if self.actor != 'local_user':
            raise AgentError('EXPLICIT_USER_RECHECK_REQUIRED', '重新运行自动检查需要明确用户动作', 403)
        req = RecheckRequest.model_validate(req.model_dump())
        payload_hash = digest(req.model_dump())
        legacy_payload_hash = digest(req.model_dump(exclude={'feedback', 'feedback_source'}))
        with self.store.transaction() as c:
            run = self.store.row(c, run_id)
            if run['status'] in ('CANCELLED', 'COMPLETED', 'COMPLETED_WITH_WARNINGS'):
                raise AgentError('NOT_RECHECKABLE', '仅等待人工复核的未发布任务可重新运行自动检查', 409)
            if req.feedback.strip() and run['workflow_id'] != 'lecture.generate':
                raise AgentError('RECHECK_FEEDBACK_UNSUPPORTED', '当前工作流不支持改进意见；可留空后重新运行自动检查', 409)
            for row in c.execute("SELECT payload_json FROM events WHERE run_id=? AND type='checks.rerun_requested' ORDER BY sequence DESC", (run_id,)):
                action = json.loads(row['payload_json'])
                if action.get('idempotency_key') == req.idempotency_key:
                    legacy_empty_feedback = ('feedback' not in action and 'feedback_source' not in action
                        and req.feedback == '' and req.feedback_source == 'user'
                        and action.get('payload_hash') == legacy_payload_hash)
                    if action.get('payload_hash') != payload_hash and not legacy_empty_feedback:
                        raise AgentError('ACTION_CONFLICT', '自动复检动作 ID 已用于不同内容', 409)
                    self._check_expected(c, run_id, req.expected_plan_revision, req.expected_plan_hash)
                    job = c.execute('SELECT * FROM jobs WHERE id=? AND run_id=?', (action['job_id'], run_id)).fetchone()
                    if job is None:
                        raise AgentError('RECHECK_STATE_INVALID', '自动复检记录对应的任务缺失；已保留原证据', 409)
                    return dict(job)
            run, plan = self._check_expected(c, run_id, req.expected_plan_revision, req.expected_plan_hash)
            if run['status'] != 'AWAITING_USER_REVIEW':
                raise AgentError('NOT_RECHECKABLE', '仅等待人工复核的未发布任务可重新运行自动检查', 409)
            if c.execute("SELECT 1 FROM jobs WHERE run_id=? AND status IN ('queued','running')", (run_id,)).fetchone():
                raise AgentError('RECHECK_JOB_ACTIVE', '任务仍在执行，不能并发启动自动复检', 409)
            approval = c.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?', (run_id, plan['revision'])).fetchone()
            if not approval or approval['hash'] != plan['hash'] or approval['input_hash'] != run['input_hash']:
                raise AgentError('APPROVAL_REQUIRED', '当前计划仍须保有原用户确认，自动复检不会代替审批', 409)
            from .budget import view, defaults_from_settings
            budget = view(self.store, c, run, defaults_from_settings(self.settings))
            if budget['baseline_unknown']:
                raise AgentError('BUDGET_BASELINE_UNKNOWN', '请先核验历史请求预算；自动复检不重置或推断预算', 409)
            superseded = [row['artifact_id'] for row in c.execute("SELECT artifact_id FROM artifacts WHERE run_id=? AND status!='superseded'", (run_id,))]
            c.execute("UPDATE artifacts SET status='superseded' WHERE run_id=? AND status!='superseded'", (run_id,))
            job = self._enqueue(c, run, 'build', digest([run_id, 'automatic-recheck', req.idempotency_key]))
            self.store.event(c, run_id, 'checks.rerun_requested', {
                'actor': self.actor, 'idempotency_key': req.idempotency_key, 'payload_hash': payload_hash,
                'job_id': job['id'], 'plan_revision': plan['revision'], 'plan_hash': plan['hash'],
                'feedback': req.feedback, 'feedback_source': req.feedback_source,
                'superseded_artifact_ids': superseded, 'request_count_preserved': run['request_count'],
                'budget_version': budget['version'], 'approval_preserved': True,
                'checkpoints_preserved': True, 'teacher_review': 'NOT_PERFORMED'})
            return job

    def retry(self, run_id):
        with self.store.transaction() as c:
            run = self.store.row(c, run_id)
            if run['status'] not in ('FAILED', 'BLOCKED'):
                raise AgentError('NOT_RETRYABLE', '当前状态无需重试', 409)
            error = json.loads(run['error_json'] or 'null')
            from .budget import view, defaults_from_settings
            budget = view(self.store, c, run, defaults_from_settings(self.settings))
            if budget['baseline_unknown']:
                raise AgentError('BUDGET_BASELINE_UNKNOWN', '请先核验历史请求预算，或明确确认新的请求上限；普通重试不改变预算', 409)
            if error and error.get('code') == 'BUDGET_EXHAUSTED':
                if budget['version'] <= error.get('budget_version', 0):
                    raise AgentError('BUDGET_EXHAUSTED', '请先明确增加所耗尽的预算，再从原失败节点重试；累计次数不会清零', 409)
            job = c.execute("SELECT * FROM jobs WHERE run_id=? AND status='failed' ORDER BY created_at DESC LIMIT 1", (run_id,)).fetchone()
            if not job:
                raise AgentError('NO_JOB', '没有可恢复任务', 409)
            c.execute("UPDATE jobs SET status='queued',error_json=NULL,lease_owner=NULL,lease_deadline=NULL WHERE id=?", (job['id'],))
            c.execute("UPDATE runs SET status='QUEUED',error_json=NULL,updated_at=? WHERE id=?", (now(), run_id))
            self.store.event(c, run_id, 'job.retry', {'job_id': job['id'], 'resume_stage': run['stage'], 'approval_preserved': True})
            return dict(c.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone())

    def cancel(self, run_id):
        with self.store.transaction() as c:
            run = self.store.row(c, run_id)
            if run['status'] in ('COMPLETED','COMPLETED_WITH_WARNINGS'):
                raise AgentError('ALREADY_COMPLETED','已交付任务不能取消',409)
            c.execute("UPDATE runs SET status='CANCELLED',updated_at=? WHERE id=?", (now(), run_id))
            c.execute("UPDATE jobs SET status='cancelled',fencing_token=fencing_token+1 WHERE run_id=? AND status IN ('queued','running')", (run_id,))
            self.store.event(c, run_id, 'run.cancelled', {'actor': self.actor})
        return self.store.get_run(run_id)

    def review(self, run_id, req: ReviewRequest):
        if self.actor!='local_user':
            raise AgentError('HUMAN_REVIEW_REQUIRED','基准驱动不能提交教师或用户逐页审核',403)
        with self.store.transaction() as c:
            run = self.store.row(c, run_id)
            a = c.execute('SELECT * FROM artifacts WHERE artifact_id=? AND run_id=?', (req.artifact_id, run_id)).fetchone()
            if not a or a['sha256'] != req.sha256 or a['revision'] != run['active_plan_revision']:
                raise AgentError('ARTIFACT_CONFLICT', '复核页已更新或不属于此任务', 409)
            if a['status'] == 'superseded':
                raise AgentError('ARTIFACT_SUPERSEDED', '该文件属于历史交付，请复核本次自动检查生成的新文件', 409)
            if a['media_type']!='image/png' and a['name']!='quality_report.json':
                raise AgentError('NOT_REVIEW_TARGET','请审核页面图片或质量报告',400)
            if run['status'] != 'AWAITING_USER_REVIEW':
                raise AgentError('NOT_REVIEWABLE', '当前产物仍有阻塞，不能用复核跳过错误', 409)
            c.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?,?,?)', (run_id, req.artifact_id, req.sha256, req.verdict, req.note, 'local_user', now()))
            self.store.event(c, run_id, 'human.review', {'artifact_id': req.artifact_id, 'sha256': req.sha256, 'verdict': req.verdict})
            pages = c.execute("SELECT * FROM artifacts WHERE run_id=? AND revision=? AND media_type='image/png' AND status!='superseded'", (run_id, run['active_plan_revision'])).fetchall()
            reviewed = c.execute("SELECT artifact_id,sha256 FROM reviews WHERE run_id=? AND verdict='pass'", (run_id,)).fetchall()
            covered = {(r['artifact_id'], r['sha256']) for r in reviewed}
            # The quality report itself also requires explicit content/decision review.
            reports = c.execute("SELECT * FROM artifacts WHERE run_id=? AND revision=? AND name='quality_report.json' AND status!='superseded'", (run_id, run['active_plan_revision'])).fetchall()
            required = list(pages) + list(reports)
            unresolved=c.execute("SELECT 1 FROM reviews rv JOIN artifacts a ON a.artifact_id=rv.artifact_id WHERE rv.run_id=? AND a.revision=? AND a.status!='superseded' AND rv.verdict='issue' LIMIT 1",(run_id,run['active_plan_revision'])).fetchone()
            if pages and reports and not unresolved and all((p['artifact_id'], p['sha256']) in covered for p in required):
                final = 'COMPLETED_WITH_WARNINGS' if json.loads(run['input_json'])['provider'] == 'mock' else 'COMPLETED'
                receipt={'schema_version':1,'run_id':run_id,'plan_revision':run['active_plan_revision'],
                         'status':final,'actor':'local_user','submitted_at':now(),
                         'reviews':[dict(r) for r in c.execute("SELECT rv.* FROM reviews rv JOIN artifacts a ON a.artifact_id=rv.artifact_id WHERE rv.run_id=? AND a.revision=? AND a.status!='superseded'",(run_id,run['active_plan_revision']))],
                         'limitations':['人工按钮记录不等于形式化证明；mock 保持演示身份。']}
                receipt_path=self.settings.workspace/'runs'/run_id/('review-'+uid()[:12]+'.json')
                write_json(receipt_path,receipt)
                c.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),run_id,run['active_plan_revision'],receipt_path.relative_to(self.settings.workspace).as_posix(),'human_review_receipt.json',digest(receipt_path.read_bytes()),'application/json','accepted',canonical({'kind':'human_review_receipt'}),now()))
                c.execute('UPDATE runs SET status=?,stage=?,updated_at=? WHERE id=?', (final, 'published', now(), run_id))
                c.execute("UPDATE artifacts SET status='accepted' WHERE run_id=? AND revision=? AND status!='superseded'", (run_id, run['active_plan_revision']))
                self.store.event(c, run_id, 'run.published', {'human_reviewed_artifacts': len(required), 'mock': json.loads(run['input_json'])['provider'] == 'mock'})
        return self.store.get_run(run_id)
