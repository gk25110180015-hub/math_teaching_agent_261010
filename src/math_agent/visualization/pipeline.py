import json
from pathlib import Path
import zipfile
from ..pipeline import Pipeline
from ..util import AgentError, digest, now, uid, write_json
from .models import Candidates, Refinement, Program, CodeReview
from .document import interactive_html
from .render import render_video, probe_program, review_evidence
from .recovery import contract_hash, failure_identity, last_failure
from .contracts import scene_requirements, confirmed_context
from .generation import generate_program


class VisualizationPipeline(Pipeline):
    def generate(self, role, context, schema):
        context = {'input': self.run['input'], **context}
        if self.run['input']['provider'] == 'mock':
            from .mock import generate
            result = generate(role, context, schema)
        else:
            result = self.provider.generate(role, context, schema)
        # Even late successful model responses cannot bypass cancellation or a lost lease.
        with self.store.transaction() as c:
            self.store.assert_fence(c, self.job)
        return result

    def plan(self):
        self.stage('PLANNING', 'visualization.plan')
        plan = self.run.get('plan')
        if plan is None:
            proposal = self.generate('visualization_candidates', {}, Candidates)
            plan = {'schema_version': 1, 'workflow_id': self.run['workflow_id'], 'title': self.run['input']['topic'],
                    'provider': self.run['input']['provider'], 'model_id': self.model_id,
                    'input_snapshot_hash': self.run['input_hash'], 'phase': 'candidates', **proposal,
                    'questions': [], 'decisions': [], 'decision_ids': [], 'sections': [],
                    'refinement_round': 0, 'question_history': [], 'unresolved_blocking_questions': ['CHOOSE_CANDIDATE']}
        elif plan.get('pending_refinement'):
            # Do not bury selected answers inside copies of every alternative.
            compact_decisions = [{**{k: v for k, v in d.items() if k not in ('answers', 'candidate')},
                'answers': [{'question': {'id': a['question']['id'], 'prompt': a['question']['prompt']},
                             'option': a['option']} for a in d['answers']],
                **({'candidate': {'id': d['candidate']['id'], 'title': d['candidate']['title']}} if d.get('candidate') else {})}
                for d in plan['decisions']]
            resolved = [{'decision_id': d['id'], 'question_id': a['question']['id'], 'question': a['question']['prompt'],
                         'selected_option_id': a['option']['id'], 'selected_label': a['option']['label'], 'effect': a['option']['effect']}
                        for d in reversed(compact_decisions) for a in d['answers']]
            context = {'current_plan': {k: v for k, v in plan.items() if k not in ('candidates', 'question_history', 'decisions')},
                       'latest_user_decision': compact_decisions[-1], 'resolved_choices': resolved,
                       'decision_ids': plan['decision_ids'], 'refinement_round': plan['refinement_round']}
            context['current_plan']['decisions'] = compact_decisions
            for attempt in range(self.settings.max_schema_repair_attempts + 1):
                result = self.generate('visualization_refine', context, Refinement)
                issues = []
                if set(result['applied_decision_ids']) != set(plan['decision_ids']):
                    issues.append('applied_decision_ids 必须完整包含所有 decision_ids，并落实对应选择。')
                if plan['refinement_round'] == 0 and not result['questions']:
                    issues.append('选定候选后的第一轮必须提出与数学内容有关的澄清选择题。')
                if any(q['id'] in {a['question_id'] for a in resolved} or q['prompt'] in {a['question'] for a in resolved}
                       for q in result['questions']):
                    issues.append('不得重新询问 resolved_choices 中已回答的问题；应将选中的 effect 写入 story。')
                if not issues:
                    break
                if attempt == self.settings.max_schema_repair_attempts:
                    raise AgentError('VISUAL_PLAN_BLOCKED', '模型规划校验未通过：' + '; '.join(issues))
                context['repair_issues'] = issues
            plan['question_history'].append({'round': plan['refinement_round'], 'questions': plan['questions']})
            plan.update(result)
            plan['title'] = result['story']['title']
            plan['refinement_round'] += 1
            plan['phase'] = 'questions' if result['questions'] else 'ready'
            plan['pending_refinement'] = None
            plan['unresolved_blocking_questions'] = [q['id'] for q in result['questions']]
        else:
            # A crash after save_plan but before finish must not regenerate or erase choices.
            self.store.finish(self.job, 'AWAITING_PLAN_INPUT' if plan['unresolved_blocking_questions'] else 'PLAN_READY', 'visualization.plan.ready')
            return plan
        with self.store.transaction() as c:
            self.store.assert_fence(c, self.job)
            saved = self.store.save_plan(c, self.run['id'], plan)
        self.store.finish(self.job, 'AWAITING_PLAN_INPUT' if plan['unresolved_blocking_questions'] else 'PLAN_READY', 'visualization.plan.ready')
        return saved

    def build(self):
        plan = self.run['plan']; approval = self.run['approval']
        if not approval or approval['hash'] != plan['hash'] or approval['input_hash'] != self.run['input_hash'] or plan['phase'] != 'ready' or plan['unresolved_blocking_questions']:
            raise AgentError('APPROVAL_REQUIRED', '请先确认当前完整可视化计划')
        self.stage('BUILDING', 'visualization.code')
        contract = contract_hash()
        seed = last_failure(self.store, self.settings.workspace, self.run)
        history = seed.get('repair_history', [])
        requirements = scene_requirements(plan['story'])
        approved_context = confirmed_context(plan)
        context = {**seed, 'confirmed_plan': approved_context, 'runtime_contract_version': 2,
                   'scene_requirements': requirements}
        repairs = self.effective_budget()['local_repairs_per_unit']
        result_dir = self.build_root / ('visual-' + uid()[:8]); result_dir.mkdir(parents=True)
        write_json(result_dir / 'plan.json', plan)
        program = None; review = None; render = None
        # Reuse validated generated code after worker restart; render is safely repeated.
        for attempt in range(repairs + 1):
            key = f'visualization.code.{attempt}'
            identity = digest({'context': context, 'contract_hash': contract})
            cached = self.store.cached_step(self.run['id'], key, identity)
            program = cached or generate_program(self.generate, context, self.settings.max_schema_repair_attempts,
                record=lambda revision, patch: write_json(result_dir / f'patch-{attempt}-{revision}.json', patch))
            program = Program.model_validate(program).model_dump()
            self.store.checkpoint(self.job, key, identity, program)
            write_json(result_dir / f'program-{attempt}.json', program)
            problems = []
            if program['runtime_version'] != 2:
                problems.append('runtime_version 必须为 2，并实现分镜演示/自由探索、有效 controls 和动态 title/caption 返回契约。')
            if set(program['covered_decision_ids']) != set(plan['decision_ids']):
                problems.append('covered_decision_ids 必须完整覆盖已确认 decision_ids，不得遗漏用户选择。')
            project = {'story': plan['story'], 'program': program, 'plan_hash': plan['hash'], 'provider': self.run['input']['provider']}
            write_json(result_dir / 'project.json', project)
            (result_dir / 'scene.js').write_text(program['code'], encoding='utf-8')
            (result_dir / 'interactive.html').write_text(interactive_html(plan['story'], program, self.run['input']['provider']), encoding='utf-8')
            self.stage('LOCAL_REVIEW', 'visualization.controls.check')
            try:
                probes = probe_program(result_dir, lambda: self.store.active(self.job))
            except AgentError as error:
                if error.code in ('CANCELLED', 'STALE_WORKER', 'LEASE_LOST'):
                    raise
                probes = {'status': 'FAIL', 'error': error.message}
            write_json(result_dir / f'probes-{attempt}.json', probes)
            evidence = review_evidence(probes)
            if probes['status'] != 'PASS':
                problems.extend(probes.get('issues') or [probes.get('error', '交互运行检查失败')])
            self.stage('LOCAL_REVIEW', 'visualization.code.review')
            review = self.generate('visualization_reviewer', {'confirmed_plan': approved_context, 'program': program,
                'scene_requirements': requirements, 'runtime_evidence': evidence, 'repair_history': history}, CodeReview)
            write_json(result_dir / f'review-{attempt}.json', review)
            problems.extend(review['issues'])
            if not problems:
                self.stage('BUILDING', 'visualization.render')
                try:
                    render = render_video(result_dir, sum(s['seconds'] for s in plan['story']['scenes']), lambda: self.store.active(self.job))
                except AgentError as error:
                    if error.code in ('CANCELLED', 'STALE_WORKER'):
                        raise
                    problems.append(error.message)
            if not problems:
                break
            problems = list(dict.fromkeys(problems))
            write_json(result_dir / f'issues-{attempt}.json', problems)
            history = [*history, {'issues': problems}]
            seed = {'previous_program': program, 'repair_issues': problems, 'repair_history': history,
                    'runtime_evidence': evidence}
            self.store.checkpoint(self.job, 'visualization.last_failure', failure_identity(self.run), seed)
            if attempt == repairs:
                diagnostics = [p for p in result_dir.iterdir() if p.suffix in ('.json', '.log', '.js')]
                self.store.publish_artifacts(self.job, [{'storage_key': p.relative_to(self.settings.workspace).as_posix(),
                    'name': p.name, 'sha256': digest(p.read_bytes()),
                    'media_type': 'application/json' if p.suffix == '.json' else 'text/plain',
                    'metadata': {'kind': 'visualization_draft', 'plan_hash': plan['hash'], 'status': 'FAILED_NOT_DELIVERED'}} for p in diagnostics])
                raise AgentError('VISUAL_QUALITY_BLOCKED', '可视化代码/渲染检查未通过：' + '; '.join(problems)[:1800])
            self.stage('REPAIRING', 'visualization.repair')
            context = {**seed, 'confirmed_plan': approved_context, 'runtime_contract_version': 2,
                       'scene_requirements': requirements}
        quality = {'status': 'PASS_WITH_REVIEW_REQUIRED', 'created_at': now(), 'plan_hash': plan['hash'],
                   'provider': self.run['input']['provider'], 'code_review': review, 'render': render,
                   'runtime_contract_version': 2, 'contract_hash': contract, 'repair_history': history,
                   'human_math_review': 'NOT_RUN', 'human_visual_review': 'NOT_RUN',
                   'limitations': program['limitations'], 'covered_decision_ids': program['covered_decision_ids'],
                   'format': 'WebM VP8/VP9, 960x540, silent animation with Chinese captions'}
        write_json(result_dir / 'quality_report.json', quality)
        (result_dir / 'README.txt').write_text('打开 interactive.html 即可离线交互。video.webm 为无声教学动画。\nscene.js 是模型生成的可编辑绘图函数；project.json 包含控件与方案。\n模型和自动运行检查不能代替教师数学与视觉审核。\n', encoding='utf-8')
        names = ['video.webm', 'interactive.html', 'scene.js', 'project.json', 'plan.json', 'quality_report.json',
                 'frame-000.png', 'frame-050.png', 'frame-100.png', 'README.txt']
        with zipfile.ZipFile(result_dir / 'source_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.write(result_dir / name, name)
        names.append('source_bundle.zip')
        media = {'.webm': 'video/webm', '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.zip': 'application/zip', '.txt': 'text/plain'}
        self.store.publish_artifacts(self.job, [{'storage_key': (result_dir / name).relative_to(self.settings.workspace).as_posix(),
            'name': name, 'sha256': digest((result_dir / name).read_bytes()), 'media_type': media[Path(name).suffix],
            'metadata': {'kind': 'visualization', 'plan_hash': plan['hash'], 'teacher_review': 'NOT_RUN'}} for name in names])
        self.store.finish(self.job, 'COMPLETED_WITH_WARNINGS', 'visualization.delivered')
