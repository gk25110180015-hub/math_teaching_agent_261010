"""Archive prior feedback proposal and narrow the supported workflow; no src edits."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
manifest_path = OUT / 'recheck-feedback-api-ui-manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
archive = OUT / 'recheck-feedback-candidate-history' / (datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
archive.mkdir(parents=True, exist_ok=False)
for name in [value['candidate'] for value in manifest['files']] + [
        manifest_path.name, 'recheck-feedback-api-ui.patch', 'recheck-feedback-api-ui.md']:
    shutil.copyfile(OUT / name, archive / name)


def replace_once(value, before, after):
    assert value.count(before) == 1, (before, value.count(before))
    return value.replace(before, after, 1)


by_source = {value['source']: value for value in manifest['files']}
service_path = OUT / by_source['src/math_agent/service.py']['candidate']
service = service_path.read_text(encoding='utf-8')
anchor = '            for row in c.execute("SELECT payload_json FROM events WHERE run_id=? AND type=\'checks.rerun_requested\' ORDER BY sequence DESC", (run_id,)):\n'
service = replace_once(service, anchor,
    "            if req.feedback.strip() and run['workflow_id'] != 'lecture.generate':\n"
    "                raise AgentError('RECHECK_FEEDBACK_UNSUPPORTED', '当前工作流不支持改进意见；可留空后重新运行自动检查', 409)\n" + anchor)
compile(service, str(service_path), 'exec')
service_path.write_text(service, encoding='utf-8', newline='\n')
ui_path = OUT / by_source['src/math_agent/web/static/app.js']['candidate']
ui = ui_path.read_text(encoding='utf-8')
ui = replace_once(ui,
    '    const feedback = el("textarea", null, { id: "recheck-feedback", rows: "3", maxlength: "10000", placeholder: "例如：增加夹逼法练习，核对两个重要极限的条件" });\n'
    '    feedback.value = state.recheckFeedback[run.id] || "";\n'
    '    feedback.oninput = () => { state.recheckFeedback[run.id] = feedback.value; };\n'
    '    c.append(field("本轮希望改进的内容（可选）", feedback, "按已批准的教学计划提出建议；系统会核查并修订适用内容。留空则执行常规自动检查。"));\n',
    '    const feedback = run.workflow_id === "lecture.generate" ? el("textarea", null, { id: "recheck-feedback", rows: "3", maxlength: "10000", placeholder: "例如：增加夹逼法练习，核对两个重要极限的条件" }) : null;\n'
    '    if (feedback) {\n'
    '      feedback.value = state.recheckFeedback[run.id] || "";\n'
    '      feedback.oninput = () => { state.recheckFeedback[run.id] = feedback.value; };\n'
    '      c.append(field("本轮希望改进的内容（可选）", feedback, "按已批准的教学计划提出建议；系统会核查并修订适用内容。留空则执行常规自动检查。"));\n'
    '    }\n')
ui = replace_once(ui, 'feedback: feedback.value, feedback_source: "user"', 'feedback: feedback?.value || "", feedback_source: "user"')
ui_path.write_text(ui, encoding='utf-8', newline='\n')
patch = []
for value in manifest['files']:
    source = ROOT / value['source']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == value['baseline_sha256']
    candidate = OUT / value['candidate']
    value['candidate_sha256'] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    patch.extend(difflib.unified_diff(source.read_text(encoding='utf-8').splitlines(keepends=True),
                                    candidate.read_text(encoding='utf-8').splitlines(keepends=True),
                                    fromfile='a/' + value['source'], tofile='b/' + value['source']))
(OUT / 'recheck-feedback-api-ui.patch').write_text(''.join(patch), encoding='utf-8', newline='\n')
manifest['candidate_revision'] = 2
manifest['superseded_candidate_archive'] = archive.relative_to(OUT).as_posix()
for key in ('isolated_candidate_regression', 'combined_api_pipeline_package_regression', 'javascript_syntax'):
    manifest.setdefault('prior_revision_evidence', {})[key] = manifest.pop(key)
manifest['workflow_scope'] = {'feedback_supported': ['lecture.generate'],
    'other_workflows_nonblank_feedback': 'RECHECK_FEEDBACK_UNSUPPORTED_HTTP_409',
    'empty_feedback': 'ORDINARY_RECHECK_REMAINS_AVAILABLE',
    'scope_red_regression': {'failed': 2, 'passed': 1,
        'evidence': 'recheck-feedback-combined/20260920-170412-fff284'},
    'revised_candidate_validation': 'NOT_RUN_YET'}
manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps({'status': 'CANDIDATE_ONLY', 'archive': str(archive),
                  'files': {value['source']: value['candidate_sha256'] for value in manifest['files']}}))
