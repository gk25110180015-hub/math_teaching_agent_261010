"""Read-only, consistent SQLite audit of already-authorized live task history."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'reports/iteration4'
INITIAL = OUTPUT / 'resume-20260920T143357-e340db'
LATEST_RETRY = OUTPUT / 'resume-20260920T152729-a563a0'
DATABASE = ROOT / 'workspace/iteration2-live/agent.db'
RUNS = {'CH02': ('fd6736af6ef14be3839e019e86ca1e5c', 33),
        'CH03': ('a45be503af594ce8aae0bb1e4c30184b', 27)}
KEYS = ('requests', 'local_repairs_per_unit', 'global_repair_rounds')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def fingerprint(path):
    return {'path': path.relative_to(ROOT).as_posix(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


summary = read(INITIAL / 'summary.json')
restart = read(OUTPUT / 'restart-preservation.json')
report = {
    'snapshot_started_utc': datetime.now(timezone.utc).isoformat(),
    'verification_mode': 'SQLITE_MODE_RO_CONSISTENT_READ_TRANSACTION_AND_SAVED_REPORTS',
    'database': DATABASE.relative_to(ROOT).as_posix(),
    'user_authorization_record': summary['authorization'],
    'initial_increase_report': fingerprint(INITIAL / 'summary.json'),
    'latest_retry_report': fingerprint(LATEST_RETRY / 'summary.json'),
    'restart_preservation_evidence': fingerprint(OUTPUT / 'restart-preservation.json'),
    'restart_preservation_recorded_status': restart['status'],
    'remote_model_calls_by_this_audit': 0, 'database_writes': 0,
    'new_human_reviews': 0, 'cases': {},
    'scope': 'Snapshot of two running live tasks. This does not assert final content quality or eventual task completion.',
}
with sqlite3.connect(DATABASE.as_uri() + '?mode=ro', uri=True, timeout=10) as connection:
    connection.row_factory = sqlite3.Row
    connection.execute('BEGIN')
    for case, (run_id, original_count) in RUNS.items():
        before = read(INITIAL / case / 'before.json')
        initial_after = read(INITIAL / case / 'after.json')
        initial_events = read(INITIAL / case / 'events.json')
        budget_request = read(INITIAL / case / 'budget-request.json')
        budget_response = read(INITIAL / case / 'budget-response.json')
        row = dict(connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone())
        approval = dict(connection.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?',
                                          (run_id, row['active_plan_revision'])).fetchone())
        plan = dict(connection.execute('SELECT revision,hash FROM plans WHERE run_id=? AND revision=?',
                                      (run_id, row['active_plan_revision'])).fetchone())
        budget = dict(connection.execute('SELECT * FROM run_budgets WHERE run_id=?', (run_id,)).fetchone())
        defaults, overrides = json.loads(budget['defaults_json']), json.loads(budget['overrides_json'])
        limits = {key: overrides.get(key, defaults.get(key)) for key in KEYS}
        actions = [dict(value) for value in connection.execute(
            'SELECT * FROM budget_actions WHERE run_id=? ORDER BY created_at', (run_id,))]
        for action in actions:
            action['before'] = json.loads(action.pop('before_json'))
            action['after'] = json.loads(action.pop('after_json'))
        events = [dict(value) for value in connection.execute(
            'SELECT sequence,type,payload_json,timestamp FROM events WHERE run_id=? ORDER BY sequence', (run_id,))]
        requests = [value for value in events if value['type'] == 'provider.request']
        old_requests = [value for value in initial_events if value['type'] == 'provider.request']
        old_normalized = [{key: value[key] for key in ('sequence', 'type', 'payload_json', 'timestamp')}
                          for value in old_requests]
        budget_events = [value for value in events if value['type'] == 'budget.increased_by_user']
        budget_payloads = [json.loads(value['payload_json']) for value in budget_events]
        reviews = connection.execute('SELECT count(*) FROM reviews WHERE run_id=?', (run_id,)).fetchone()[0]
        checkpoints = []
        for directory in sorted(OUTPUT.glob('resume-*')):
            for moment in ('before', 'after'):
                path = directory / case / (moment + '.json')
                if path.is_file():
                    snapshot = read(path)
                    checkpoints.append({'report': path.relative_to(ROOT).as_posix(), 'sha256': fingerprint(path)['sha256'],
                                        'request_count': snapshot['request_count'], 'status': snapshot['status'],
                                        'approval_preserved': snapshot['approval'] == before['approval'],
                                        'plan_hash_preserved': snapshot['plan']['hash'] == before['plan']['hash'],
                                        'input_hash_preserved': snapshot['input_hash'] == before['input_hash']})
        counts = [value['request_count'] for value in checkpoints] + [row['request_count']]
        checks = {
            'original_request_count_expected': before['request_count'] == original_count,
            'increase_itself_preserved_request_count': initial_after['request_count'] == budget_response['request_count'] == original_count,
            'original_plan_revision_and_hash_preserved': plan['revision'] == before['active_plan_revision'] and plan['hash'] == before['plan']['hash'],
            'original_approval_record_preserved': approval == before['approval'],
            'original_input_hash_preserved': row['input_hash'] == before['input_hash'],
            'all_saved_snapshots_preserve_approval_input_and_plan': all(
                value['approval_preserved'] and value['plan_hash_preserved'] and value['input_hash_preserved'] for value in checkpoints),
            'saved_request_counts_nondecreasing': all(a <= b for a, b in zip(counts, counts[1:])),
            'request_counter_matches_full_provider_request_ledger': len(requests) == row['request_count'],
            'original_request_prefix_unchanged': len(old_requests) == original_count and requests[:original_count] == old_normalized,
            'remaining_requests_are_append_only': row['request_count'] >= original_count and len(requests[original_count:]) == row['request_count'] - original_count,
            'exactly_one_recorded_explicit_budget_action': len(actions) == 1 and actions[0]['action_id'] == budget_request['action_id'],
            'budget_limits_240_6_6': limits == {'requests': 240, 'local_repairs_per_unit': 6, 'global_repair_rounds': 6},
            'budget_version_preserved_after_first_increase': budget['version'] == 1,
            'budget_action_before_and_after_correct': len(actions) == 1
                and {key: actions[0]['before'][key] for key in KEYS} == {'requests': 60, 'local_repairs_per_unit': 2, 'global_repair_rounds': 2}
                and {key: actions[0]['after'][key] for key in KEYS} == limits,
            'budget_event_preserves_original_count_and_approval': len(budget_payloads) == 1
                and budget_payloads[0]['request_count_preserved'] == original_count
                and budget_payloads[0]['approval_preserved'] is True
                and budget_payloads[0]['action_id'] == budget_request['action_id'],
            'no_human_reviews_recorded': reviews == 0,
        }
        ledger = []
        for index, request in enumerate(requests, 1):
            payload = json.loads(request['payload_json'])
            ledger.append({'ordinal': index, 'event_sequence': request['sequence'], 'timestamp': request['timestamp'],
                           'role': payload.get('role'), 'model_id': payload.get('model_id'), 'model': payload.get('model'),
                           'payload_sha256': hashlib.sha256(request['payload_json'].encode('utf-8')).hexdigest()})
        audit_events = []
        for event in events:
            if event['type'] in ('budget.increased_by_user', 'job.retry'):
                audit_events.append({key: event[key] for key in ('sequence', 'type', 'timestamp')} | {'payload': json.loads(event['payload_json'])})
        report['cases'][case] = {
            'status': 'PASS' if all(checks.values()) else 'NOT_PASS', 'run_id': run_id, 'checks': checks,
            'original_request_count': original_count, 'current_request_count': row['request_count'],
            'appended_request_events': len(requests) - original_count, 'request_event_count': len(requests),
            'run_status_at_snapshot': row['status'], 'run_stage_at_snapshot': row['stage'],
            'active_plan': plan, 'approval': approval, 'budget_limits': limits, 'budget_version': budget['version'],
            'budget_actions': actions, 'saved_snapshot_chain': checkpoints,
            'request_ledger': ledger, 'budget_and_retry_events': audit_events, 'human_review_count': reviews,
        }
    connection.rollback()
report['snapshot_finished_utc'] = datetime.now(timezone.utc).isoformat()
report['status'] = 'PASS' if all(value['status'] == 'PASS' for value in report['cases'].values()) else 'NOT_PASS'
with (OUTPUT / 'budget-authorization-and-preservation.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
lines = [
    '# 预算授权与历史保留核对', '',
    f"结果：**{report['status']}**。只读一致性快照时间（UTC）：{report['snapshot_finished_utc']}。", '',
    '用户已明确授权提高第二、三章每单元修复及每任务请求上限，并继续真实测试。'
    '首次实际 HTTP 增额将请求 60→240、每单元局部修复 2→6、全局修复轮次 2→6；预算版本 0→1。'
    '两章各有一条匹配 action_id 的持久化预算动作和审计事件。', '',
    '| 任务 | 增额前累计请求 | 本快照累计请求 | 新增请求账本项 | 原批准计划 | 核对 |',
    '|---|---:|---:|---:|---|---|',
]
for case, value in report['cases'].items():
    lines.append(f"| {case} | {value['original_request_count']} | {value['current_request_count']} | "
                 f"{value['appended_request_events']} | revision {value['active_plan']['revision']} | {value['status']} |")
lines.extend([
    '', '核对原审批整行、输入哈希和计划哈希保持不变；全部保存的重试前后快照请求数单调不降。'
    '原 33/27 次 provider.request 事件前缀逐项保持一致，当前请求数与完整请求事件账本相等。'
    '请求计数包含已发起但失败或尚未返回的尝试，不等于成功调用数。真实任务仍在运行，本表仅是带时间戳的快照。', '',
    '本次审计仅以 SQLite mode=ro 和同一个短只读事务查询；未调用模型、未改 DB、未提交人工审核。'
    '两章人审记录均为 0。跨重启表级一致性沿用已有 restart-preservation 的 PASS 证据，本次不重复操作或重启服务。', '',
    '- [首次增额及恢复记录](resume-20260920T143357-e340db/summary.json)',
    '- [部署后再次恢复记录](resume-20260920T152729-a563a0/summary.json)',
    '- [重启保留核对](restart-preservation.json)',
    '- [逐项检查、全部请求事件序号与快照链](budget-authorization-and-preservation.json)', '',
])
for case, value in report['cases'].items():
    failures = [key for key, ok in value['checks'].items() if not ok]
    if failures:
        lines.append(f"{case} 未通过检查：{', '.join(failures)}。不得将本报告视为保留验证通过。")
with (OUTPUT / 'budget-authorization-and-preservation.md').open('x', encoding='utf-8') as stream:
    stream.write('\n'.join(lines) + '\n')
print(json.dumps({'status': report['status'], 'cases': {
    case: {'status': value['status'], 'from': value['original_request_count'], 'to': value['current_request_count'],
           'failed_checks': [key for key, ok in value['checks'].items() if not ok]}
    for case, value in report['cases'].items()}}))
