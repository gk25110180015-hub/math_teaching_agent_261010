"""Build reviewable proposal files only; never edit production source."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def replace_once(text, before, after):
    assert text.count(before) == 1, (before, text.count(before))
    return text.replace(before, after, 1)


method = '''    def recheck(self, run_id, req: ExecuteRequest):
        if self.actor != 'local_user':
            raise AgentError('EXPLICIT_USER_RECHECK_REQUIRED', '重新运行自动检查需要明确用户动作', 403)
        payload_hash = digest(req.model_dump())
        with self.store.transaction() as c:
            run = self.store.row(c, run_id)
            if run['status'] in ('CANCELLED', 'COMPLETED', 'COMPLETED_WITH_WARNINGS'):
                raise AgentError('NOT_RECHECKABLE', '仅等待人工复核的未发布任务可重新运行自动检查', 409)
            for row in c.execute("SELECT payload_json FROM events WHERE run_id=? AND type='checks.rerun_requested' ORDER BY sequence DESC", (run_id,)):
                action = json.loads(row['payload_json'])
                if action.get('idempotency_key') == req.idempotency_key:
                    if action.get('payload_hash') != payload_hash:
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
                'superseded_artifact_ids': superseded, 'request_count_preserved': run['request_count'],
                'budget_version': budget['version'], 'approval_preserved': True,
                'checkpoints_preserved': True, 'teacher_review': 'NOT_PERFORMED'})
            return job

'''

source_paths = ['src/math_agent/service.py', 'src/math_agent/web/app.py', 'src/math_agent/web/static/app.js']
originals = {name: (ROOT / name).read_text(encoding='utf-8') for name in source_paths}
service = replace_once(originals[source_paths[0]], '    def retry(self, run_id):\n', method + '    def retry(self, run_id):\n')
service = replace_once(service,
    "            if a['media_type']!='image/png' and a['name']!='quality_report.json':",
    "            if a['status'] == 'superseded':\n                raise AgentError('ARTIFACT_SUPERSEDED', '该文件属于历史交付，请复核本次自动检查生成的新文件', 409)\n            if a['media_type']!='image/png' and a['name']!='quality_report.json':")
service = replace_once(service, "AND media_type='image/png'\", (run_id, run['active_plan_revision']))",
                       "AND media_type='image/png' AND status!='superseded'\", (run_id, run['active_plan_revision']))")
service = replace_once(service, "AND name='quality_report.json'\", (run_id, run['active_plan_revision']))",
                       "AND name='quality_report.json' AND status!='superseded'\", (run_id, run['active_plan_revision']))")
service = replace_once(service, "AND a.revision=? AND rv.verdict='issue' LIMIT 1", "AND a.revision=? AND a.status!='superseded' AND rv.verdict='issue' LIMIT 1")
service = replace_once(service, "'reviews':[dict(r) for r in c.execute('SELECT * FROM reviews WHERE run_id=?',(run_id,))],",
                       "'reviews':[dict(r) for r in c.execute(\"SELECT rv.* FROM reviews rv JOIN artifacts a ON a.artifact_id=rv.artifact_id WHERE rv.run_id=? AND a.revision=? AND a.status!='superseded'\",(run_id,run['active_plan_revision']))],")
service = replace_once(service, "UPDATE artifacts SET status='accepted' WHERE run_id=? AND revision=?", "UPDATE artifacts SET status='accepted' WHERE run_id=? AND revision=? AND status!='superseded'")

api = replace_once(originals[source_paths[1]], "    @app.post('/api/runs/{run_id}/retry',status_code=202)\n",
    "    @app.post('/api/runs/{run_id}/recheck',status_code=202)\n    def recheck(run_id:str,data:ExecuteRequest): return service.recheck(run_id,data)\n\n    @app.post('/api/runs/{run_id}/retry',status_code=202)\n")

ui = replace_once(originals[source_paths[2]], '  if (["FAILED", "BLOCKED"].includes(run.status)) actions.append(button(',
    '''  if (run.status === "AWAITING_USER_REVIEW") {
    const previousBuild = (run.jobs || []).filter(job => job.kind === "build").at(-1);
    actions.append(button("重新运行自动检查", async () => {
      await api(`/api/runs/${run.id}/recheck`, { expected_plan_revision: run.plan.revision, expected_plan_hash: run.plan.hash, idempotency_key: `${run.id}:recheck:${previousBuild?.id || run.plan.hash}` });
      await refreshRun(true); await refreshList();
    }, "", { id: "recheck-run", disabled: run.budget?.baseline_unknown || (run.jobs || []).some(job => ["queued", "running"].includes(job.status)) }));
    c.append(el("p", "自动复检会重新检查已保存内容并生成本次交付；沿用原计划和累计预算，历史文件保留。此操作不提交人工审核。", { class: "hint" }));
  }
  if (["FAILED", "BLOCKED"].includes(run.status)) actions.append(button(''')
ui = replace_once(ui, '  const artifacts = run.artifacts || []; if (!artifacts.length) return;',
    '''  const allArtifacts = run.artifacts || []; if (!allArtifacts.length) return;
  const artifacts = allArtifacts.filter(artifact => artifact.status !== "superseded");
  const historicalArtifacts = allArtifacts.filter(artifact => artifact.status === "superseded");''')
ui = replace_once(ui, '  c.append(links);\n  if (run.workflow_id === "beamer.from_tex"',
    '''  c.append(links);
  if (historicalArtifacts.length) {
    const history = append(el("details", null, { id: "artifact-history" }), el("summary", `历史交付 · ${historicalArtifacts.length} 个文件`), el("p", "以下文件已由后续自动检查替代，保留供比较和下载。本次预览及人工复核使用当前文件。", { class: "hint" }));
    const historyLinks = el("div", null, { class: "artifact-list" });
    for (const artifact of historicalArtifacts) {
      const link = el("a", null, { href: artifactUrl(artifact), class: "artifact-link", target: "_blank", rel: "noopener", "data-historical-artifact-id": artifact.artifact_id });
      append(link, el("strong", artifact.name || artifact.artifact_id), el("small", `历史交付 · 计划版本 ${artifact.revision ?? "待记录"} · ${artifact.created_at || "时间未记录"}`), el("small", `SHA-256 ${artifact.sha256 || "待记录"}`, { class: "hash" }));
      historyLinks.append(link);
    }
    history.append(historyLinks); c.append(history);
  }
  if (run.workflow_id === "beamer.from_tex"''')

proposals = dict(zip(source_paths, [service, api, ui]))
manifest = {'status': 'PROPOSED_NOT_APPLIED', 'files': [], 'red_regression': {'passed': 1, 'failed': 12},
            'real_api': 'NOT_RUN', 'windows_compile': 'NOT_RUN', 'real_browser': 'NOT_RUN', 'teacher_review': 'NOT_RUN'}
diffs = []
for name, text in proposals.items():
    if name.endswith('.py'):
        compile(text, name + '.proposed', 'exec')
    target = OUT / ('automatic-recheck-' + name.replace('/', '_') + '.proposed')
    target.write_text(text, encoding='utf-8', newline='\n')
    diffs.extend(difflib.unified_diff(originals[name].splitlines(keepends=True), text.splitlines(keepends=True),
                                    fromfile='a/' + name, tofile='b/' + name))
    manifest['files'].append({'source': name, 'proposal': target.name,
        'baseline_sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
        'proposal_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    assert (ROOT / name).read_text(encoding='utf-8') == originals[name]
(OUT / 'automatic-recheck-fix.patch').write_text(''.join(diffs), encoding='utf-8', newline='\n')
(OUT / 'automatic-recheck-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(manifest))
