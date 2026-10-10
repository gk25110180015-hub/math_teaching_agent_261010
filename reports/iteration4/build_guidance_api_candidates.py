"""Prepare the HTTP/API portion of explicit scoped recovery, without deploying."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'repair-guidance-api-candidate'


def replace(text, old, new):
    assert text.count(old) == 1, old[:120]
    return text.replace(old, new, 1)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    source = ROOT/'src/math_agent/domain.py'
    domain = replace(source.read_text(encoding='utf-8'), '\n\nclass ReviewRequest(StrictModel):', '''

class RepairGuidanceRequest(StrictModel):
    expected_plan_revision: int
    expected_plan_hash: str
    action_id: str = Field(min_length=1, max_length=128)
    section_id: str = Field(pattern=r'^S[0-9]+$')
    expected_candidate_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    unit_ids: list[str] = Field(min_length=1, max_length=8)
    instructions: str = Field(min_length=20, max_length=20000)
    source: Literal['user', 'agent_audit'] = 'user'

    @model_validator(mode='after')
    def bounded_guidance(self):
        self.instructions = self.instructions.strip()
        if len(self.instructions) < 20 or len(self.unit_ids) != len(set(self.unit_ids)):
            raise ValueError('Use distinct actual unit IDs and a concrete repair instruction')
        if any(not value.strip() or len(value) > 120 for value in self.unit_ids):
            raise ValueError('Unit IDs must be nonempty and bounded')
        return self


class ReviewRequest(StrictModel):''')
    source = ROOT/'src/math_agent/service.py'
    service = replace(source.read_text(encoding='utf-8'), 'RecheckRequest, DecisionsRequest,', 'RecheckRequest, RepairGuidanceRequest, DecisionsRequest,')
    service = replace(service, "        run['feedback_review'] = self.feedback_review(run)\n", """        run['feedback_review'] = self.feedback_review(run)
        from .repair_guidance import guidance_context
        try:
            run['repair_guidance_context'] = guidance_context(self.settings, run)
        except AgentError as error:
            run['repair_guidance_context'] = None
            run['repair_guidance_context_error'] = {'code': error.code, 'message': error.message}
""")
    begin = service.index('    def retry(self, run_id):\n')
    end = service.index('    def cancel(self, run_id):\n', begin)
    old = service[begin:end]
    body = old[old.index('            if run[\'status\']'):]
    body = ''.join(line[4:] if line.startswith('    ') else line for line in body.splitlines(True))
    replacement = '''    def request_repair_guidance(self, run_id, req: RepairGuidanceRequest):
        if self.actor != 'local_user':
            raise AgentError('EXPLICIT_USER_GUIDANCE_REQUIRED', '修复建议必须由明确的本地操作提交', 403)
        req = RepairGuidanceRequest.model_validate(req.model_dump())
        payload_hash = digest(req.model_dump())
        with self.store.transaction() as c:
            run, plan = self._check_expected(c, run_id, req.expected_plan_revision, req.expected_plan_hash)
            if run['status'] in ('CANCELLED', 'COMPLETED', 'COMPLETED_WITH_WARNINGS'):
                raise AgentError('GUIDANCE_NOT_ALLOWED', '已取消或发布任务不能据此继续修改', 409)
            for row in c.execute("SELECT payload_json FROM events WHERE run_id=? AND type='repair.guidance_requested' ORDER BY sequence DESC", (run_id,)):
                previous = json.loads(row['payload_json'])
                if previous.get('action_id') == req.action_id:
                    if previous.get('payload_hash') != payload_hash:
                        raise AgentError('ACTION_CONFLICT', '同一修复动作已用于不同内容', 409)
                    job = c.execute('SELECT * FROM jobs WHERE id=? AND run_id=?', (previous['job_id'], run_id)).fetchone()
                    if job is None:
                        raise AgentError('GUIDANCE_STATE_INVALID', '修复动作对应的任务缺失，原记录保留', 409)
                    return dict(job)
            if run['workflow_id'] != 'lecture.generate' or run['status'] not in ('BLOCKED', 'FAILED'):
                raise AgentError('GUIDANCE_NOT_ALLOWED', '仅有已保存正文的受阻讲义可提交定点修复建议', 409)
            if c.execute("SELECT 1 FROM jobs WHERE run_id=? AND status IN ('queued','running')", (run_id,)).fetchone():
                raise AgentError('GUIDANCE_JOB_ACTIVE', '当前任务尚未停稳，不能同时提交修复建议', 409)
            approval = c.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?', (run_id, plan['revision'])).fetchone()
            if not approval or approval['hash'] != plan['hash'] or approval['input_hash'] != run['input_hash']:
                raise AgentError('APPROVAL_REQUIRED', '修复必须保留当前计划的原批准，建议不代替批准', 409)
            from .repair_guidance import guidance_context
            context = guidance_context(self.settings, self.store.get_run(run_id))
            if not context or context['section_id'] != req.section_id:
                raise AgentError('GUIDANCE_SCOPE_UNAVAILABLE', '当前失败没有可核实的相应局部正文；原状态保留', 409)
            if context['candidate_hash'] != req.expected_candidate_hash:
                raise AgentError('GUIDANCE_CANDIDATE_CHANGED', '实际正文已经变化，请查看新正文后重新提交', 409)
            actual = {unit['id'] for unit in context['units']}
            if not set(req.unit_ids).issubset(actual):
                raise AgentError('GUIDANCE_SCOPE_INVALID', '修复目标必须是当前失败节已有的实际单元', 409)
            from .budget import view, defaults_from_settings
            budget = view(self.store, c, run, defaults_from_settings(self.settings))
            job = c.execute("SELECT * FROM jobs WHERE run_id=? AND status='failed' ORDER BY created_at DESC,rowid DESC LIMIT 1", (run_id,)).fetchone()
            if not job or job['kind'] != 'build':
                raise AgentError('GUIDANCE_NOT_ALLOWED', '只有原讲义构建任务可从此入口恢复', 409)
            self.store.event(c, run_id, 'repair.guidance_requested', {
                'action_id': req.action_id, 'payload_hash': payload_hash, 'job_id': job['id'],
                'plan_hash': plan['hash'], 'plan_revision': plan['revision'],
                'section_id': req.section_id, 'candidate_hash': context['candidate_hash'],
                'candidate_key': context['candidate_key'], 'candidate_file_hash': context['candidate_file_hash'],
                'recovery_binding': context['recovery_binding'], 'unit_ids': req.unit_ids,
                'instructions': req.instructions, 'source': req.source, 'actor': self.actor,
                'request_count_preserved': run['request_count'], 'budget_version': budget['version'],
                'approval_preserved': True, 'teacher_review': 'NOT_RUN',
                'meaning': 'Scoped repair proposal requested; not a mathematical verdict or new plan authorization'})
            return self._retry_locked(c, run)

    def retry(self, run_id):
        with self.store.transaction() as c:
            return self._retry_locked(c, self.store.row(c, run_id))

    def _retry_locked(self, c, run):
        run_id = run['id']
''' + body
    replacement = replacement.replace("ORDER BY created_at DESC LIMIT 1", "ORDER BY created_at DESC,rowid DESC LIMIT 1")
    service = service[:begin] + replacement + service[end:]
    source = ROOT/'src/math_agent/web/app.py'
    web = replace(source.read_text(encoding='utf-8'), 'RecheckRequest, ReviewRequest,', 'RecheckRequest, RepairGuidanceRequest, ReviewRequest,')
    web = replace(web, "    @app.post('/api/runs/{run_id}/retry',status_code=202)\n", """    @app.post('/api/runs/{run_id}/repair-guidance',status_code=202)
    def repair_guidance(run_id:str,data:RepairGuidanceRequest): return service.request_repair_guidance(run_id,data)

    @app.post('/api/runs/{run_id}/retry',status_code=202)
""")
    files = []
    for name, text in [('domain.py', domain), ('service.py', service), ('web/app.py', web)]:
        ast.parse(text)
        candidate = OUT/(name.replace('/', '-') + '.candidate.py')
        candidate.write_text(text, encoding='utf-8', newline='\n')
        files.append({'source': 'src/math_agent/' + name, 'candidate': candidate.relative_to(OUT.parent).as_posix(),
                      'baseline_sha256': sha(ROOT/'src/math_agent'/name), 'candidate_sha256': sha(candidate)})
    (OUT/'manifest.json').write_text(json.dumps({'status': 'CANDIDATE_NOT_VALIDATED', 'files': files}, indent=2), encoding='utf-8')
    print(json.dumps({'folder': str(OUT), 'files': len(files), 'status': 'CANDIDATE_NOT_VALIDATED'}))


if __name__ == '__main__':
    main()
