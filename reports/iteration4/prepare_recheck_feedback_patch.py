"""Generate isolated API/UI feedback candidates; never edit production source."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
paths = ['src/math_agent/domain.py', 'src/math_agent/service.py',
         'src/math_agent/web/app.py', 'src/math_agent/web/static/app.js']
originals = {name: (ROOT / name).read_text(encoding='utf-8') for name in paths}


def replace_once(text, before, after):
    assert text.count(before) == 1, (before, text.count(before))
    return text.replace(before, after, 1)


domain = replace_once(originals[paths[0]], 'class ReviewRequest(StrictModel):',
    "class RecheckRequest(ExecuteRequest):\n"
    "    feedback: str = Field(default='', max_length=10000)\n"
    "    feedback_source: Literal['user', 'agent_audit'] = 'user'\n\n\n"
    'class ReviewRequest(StrictModel):')
service = replace_once(originals[paths[1]], 'ConfirmRequest, ExecuteRequest, DecisionsRequest',
                       'ConfirmRequest, ExecuteRequest, RecheckRequest, DecisionsRequest')
service = replace_once(service,
    "    def recheck(self, run_id, req: ExecuteRequest):\n"
    "        if self.actor != 'local_user':\n"
    "            raise AgentError('EXPLICIT_USER_RECHECK_REQUIRED', '重新运行自动检查需要明确用户动作', 403)\n"
    "        payload_hash = digest(req.model_dump())\n",
    "    def recheck(self, run_id, req: RecheckRequest):\n"
    "        if self.actor != 'local_user':\n"
    "            raise AgentError('EXPLICIT_USER_RECHECK_REQUIRED', '重新运行自动检查需要明确用户动作', 403)\n"
    "        req = RecheckRequest.model_validate(req.model_dump())\n"
    "        payload_hash = digest(req.model_dump())\n"
    "        legacy_payload_hash = digest(req.model_dump(exclude={'feedback', 'feedback_source'}))\n")
service = replace_once(service,
    "                    if action.get('payload_hash') != payload_hash:\n"
    "                        raise AgentError('ACTION_CONFLICT', '自动复检动作 ID 已用于不同内容', 409)\n",
    "                    legacy_empty_feedback = ('feedback' not in action and 'feedback_source' not in action\n"
    "                        and req.feedback == '' and req.feedback_source == 'user'\n"
    "                        and action.get('payload_hash') == legacy_payload_hash)\n"
    "                    if action.get('payload_hash') != payload_hash and not legacy_empty_feedback:\n"
    "                        raise AgentError('ACTION_CONFLICT', '自动复检动作 ID 已用于不同内容', 409)\n")
service = replace_once(service,
    "                'job_id': job['id'], 'plan_revision': plan['revision'], 'plan_hash': plan['hash'],\n",
    "                'job_id': job['id'], 'plan_revision': plan['revision'], 'plan_hash': plan['hash'],\n"
    "                'feedback': req.feedback, 'feedback_source': req.feedback_source,\n")
web = replace_once(originals[paths[2]], 'ConfirmRequest, ExecuteRequest, ReviewRequest',
                   'ConfirmRequest, ExecuteRequest, RecheckRequest, ReviewRequest')
web = replace_once(web, 'def recheck(run_id:str,data:ExecuteRequest):',
                   'def recheck(run_id:str,data:RecheckRequest):')
ui = replace_once(originals[paths[3]], 'events: [], selected:', 'events: [], recheckFeedback: {}, selected:')
ui = replace_once(ui,
    '    const previousBuild = (run.jobs || []).filter(job => job.kind === "build").at(-1);\n',
    '    const previousBuild = (run.jobs || []).filter(job => job.kind === "build").at(-1);\n'
    '    const feedback = el("textarea", null, { id: "recheck-feedback", rows: "3", maxlength: "10000", placeholder: "例如：增加夹逼法练习，核对两个重要极限的条件" });\n'
    '    feedback.value = state.recheckFeedback[run.id] || "";\n'
    '    feedback.oninput = () => { state.recheckFeedback[run.id] = feedback.value; };\n'
    '    c.append(field("本轮希望改进的内容（可选）", feedback, "按已批准的教学计划提出建议；系统会核查并修订适用内容。留空则执行常规自动检查。"));\n')
ui = replace_once(ui,
    '      await api(`/api/runs/${run.id}/recheck`, { expected_plan_revision: run.plan.revision, expected_plan_hash: run.plan.hash, idempotency_key: `${run.id}:recheck:${previousBuild?.id || run.plan.hash}` });\n',
    '      await api(`/api/runs/${run.id}/recheck`, { expected_plan_revision: run.plan.revision, expected_plan_hash: run.plan.hash, idempotency_key: `${run.id}:recheck:${previousBuild?.id || run.plan.hash}`, feedback: feedback.value, feedback_source: "user" });\n'
    '      delete state.recheckFeedback[run.id];\n')

manifest = {'status': 'PROPOSED_NOT_APPLIED', 'files': [],
            'red_regression': {'failed': 12, 'passed': 6},
            'real_api': 'NOT_RUN', 'windows_compile': 'NOT_RUN',
            'real_browser': 'NOT_RUN', 'teacher_review': 'NOT_RUN'}
patch = []
for name, candidate in zip(paths, [domain, service, web, ui]):
    if name.endswith('.py'):
        compile(candidate, name + '.proposed', 'exec')
    extension = '.js' if name.endswith('.js') else '.py'
    target = OUT / ('recheck-feedback-' + name.replace('/', '_').rsplit('.', 1)[0] + '.candidate' + extension)
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(candidate)
    patch.extend(difflib.unified_diff(originals[name].splitlines(keepends=True), candidate.splitlines(keepends=True),
                                    fromfile='a/' + name, tofile='b/' + name))
    manifest['files'].append({'source': name, 'candidate': target.name,
                             'baseline_sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
                             'candidate_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    assert (ROOT / name).read_text(encoding='utf-8') == originals[name]
with (OUT / 'recheck-feedback-api-ui.patch').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(''.join(patch))
with (OUT / 'recheck-feedback-api-ui-manifest.json').open('x', encoding='utf-8') as stream:
    json.dump(manifest, stream, indent=2)
print(json.dumps(manifest))
