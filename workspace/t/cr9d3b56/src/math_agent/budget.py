"""Persist initial execution budgets; only explicit user actions can increase them."""
import json
from pathlib import Path

from pydantic import Field, model_validator

from .domain import StrictModel
from .util import AgentError, canonical, digest, now

KEYS = ('requests', 'local_repairs_per_unit', 'global_repair_rounds')
MAXIMUMS = {'requests': 1000, 'local_repairs_per_unit': 20, 'global_repair_rounds': 20}


class BudgetIncrease(StrictModel):
    expected_version: int = Field(ge=0)
    expected_plan_revision: int | None = None
    expected_plan_hash: str | None = None
    requests: int | None = Field(default=None, ge=1, le=1000)
    local_repairs_per_unit: int | None = Field(default=None, ge=1, le=20)
    global_repair_rounds: int | None = Field(default=None, ge=1, le=20)
    confirm_unknown_request_limit: bool = False
    action_id: str = Field(min_length=1, max_length=128)
    note: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def explicit_choice(self):
        if not any(getattr(self, key) is not None for key in KEYS) or not self.note.strip():
            raise ValueError('Choose at least one budget increase and provide a reason')
        return self


def defaults_from_settings(settings):
    return {'requests': settings.max_requests_per_run,
            'local_repairs_per_unit': settings.max_local_repair_attempts,
            'global_repair_rounds': getattr(settings, 'max_global_repair_rounds', 2)}


def validate_defaults(values):
    if not isinstance(values, dict) or not values or not set(values).issubset(KEYS):
        raise ValueError('Unknown or missing initial budget fields')
    for key, value in values.items():
        minimum = 1 if key == 'requests' else 0
        if type(value) is not int or not minimum <= value <= MAXIMUMS[key]:
            raise ValueError('Initial budget must be a bounded integer')


def view(store, connection, run, defaults=None):
    if defaults is not None:
        validate_defaults(defaults)
    row = connection.execute('SELECT * FROM run_budgets WHERE run_id=?', (run['id'],)).fetchone()
    base = json.loads(row['defaults_json']) if row else {}
    overrides = json.loads(row['overrides_json']) if row else {}
    limits = {**(defaults or {}), **base, **overrides}
    unknown = run['request_count'] > 0 and 'requests' not in base
    if unknown:
        limits['requests'] = None
    return {**{key: limits.get(key) for key in KEYS}, 'version': row['version'] if row else 0,
            'initialized': row is not None, 'initialized_fields': list(base),
            'source': row['source'] if row else ('LEGACY_BASELINE_UNKNOWN' if unknown else 'PENDING_FIRST_EXECUTION'),
            'baseline_unknown': unknown,
            'request_count': run['request_count'], 'defaults': base, 'overrides': overrides,
            'maximums': MAXIMUMS,
            'limitations': ['旧任务的历史请求上限未核验，不能采用当前服务默认值。须核验历史记录，或由用户明确确认一个新的请求上限；仅修改修复预算不能恢复执行。'] if unknown else ([] if row else ['首次执行时会锁定初始预算；此处显示当前配置。'])}


def initialize_in_transaction(store, connection, run, defaults, source, *, verified_legacy=False):
    validate_defaults(defaults)
    row = connection.execute('SELECT * FROM run_budgets WHERE run_id=?', (run['id'],)).fetchone()
    recorded = json.loads(row['defaults_json']) if row else {}
    if run['request_count'] > 0 and 'requests' not in recorded and not verified_legacy:
        raise AgentError('BUDGET_BASELINE_UNKNOWN', '旧任务的请求预算未知；请先核验历史预算，或明确确认新的请求上限，原请求计数保持不变', 409)
    if row:
        base = json.loads(row['defaults_json'])
        added = {key: value for key, value in defaults.items() if key not in base}
        if added:
            base.update(added)
            connection.execute('UPDATE run_budgets SET defaults_json=?,updated_at=? WHERE run_id=?',
                               (canonical(base), now(), run['id']))
            store.event(connection, run['id'], 'budget.initial_fields_recorded', {'fields': added, 'source': source})
    else:
        connection.execute('INSERT INTO run_budgets VALUES(?,?,?,?,?,?,?)',
                           (run['id'], 0, canonical(defaults), '{}', source, now(), now()))
        store.event(connection, run['id'], 'budget.initialized',
                    {'defaults': defaults, 'source': source, 'existing_request_count': run['request_count'],
                     'historical_limit_inferred': False})
    return view(store, connection, run, defaults)


def increase(store, run_id, request, defaults, actor):
    if actor != 'local_user':
        raise AgentError('EXPLICIT_USER_BUDGET_REQUIRED', '只有明确用户动作可以增加预算，基准驱动不能代填', 403)
    payload = request.model_dump()
    with store.transaction() as connection:
        run = store.row(connection, run_id)
        old = connection.execute('SELECT * FROM budget_actions WHERE run_id=? AND action_id=?',
                                 (run_id, request.action_id)).fetchone()
        if old:
            if old['payload_hash'] != digest(payload):
                raise AgentError('ACTION_CONFLICT', '预算动作 ID 已用于不同内容', 409)
            return json.loads(old['after_json'])
        if run['status'] != 'BLOCKED':
            raise AgentError('BUDGET_NOT_BLOCKED', '仅阻塞且停止执行的任务可以显式增加预算', 409)
        if connection.execute("SELECT 1 FROM jobs WHERE run_id=? AND status IN ('queued','running')", (run_id,)).fetchone():
            raise AgentError('BUDGET_JOB_ACTIVE', '任务仍有活动执行，不能并发改变预算', 409)
        plan = store.current_plan(connection, run)
        if (request.expected_plan_revision != run['active_plan_revision'] or
                request.expected_plan_hash != (plan['hash'] if plan else None)):
            raise AgentError('PLAN_CONFLICT', '计划已变化，请刷新后核对预算操作', 409)
        before = view(store, connection, run, defaults)
        if request.expected_version != before['version']:
            raise AgentError('BUDGET_CONFLICT', '预算已经变化，请刷新后重新核对', 409)
        updates = {key: value for key in KEYS if (value := getattr(request, key)) is not None}
        if before['baseline_unknown'] and ('requests' not in updates or not request.confirm_unknown_request_limit):
            raise AgentError('BUDGET_BASELINE_UNKNOWN', '历史请求上限未知；必须明确填写并确认新的请求上限，不能仅提高修复预算', 409)
        if any(before[key] is not None and value <= before[key] for key, value in updates.items()):
            raise AgentError('BUDGET_MUST_INCREASE', '所填写的每项预算都必须严格增加；留空保持原值', 400)
        if 'requests' in updates and updates['requests'] <= run['request_count']:
            raise AgentError('BUDGET_ALREADY_USED', '新的请求上限须大于已经累计的请求数', 400)
        baseline = {**defaults, **({'requests': updates['requests']} if before['baseline_unknown'] else {})}
        initialize_in_transaction(store, connection, run, baseline,
            'EXPLICIT_USER_NEW_LIMIT_HISTORY_UNKNOWN' if before['baseline_unknown'] else 'EXPLICIT_USER_CURRENT_SETTINGS',
            verified_legacy=before['baseline_unknown'])
        overrides = {**before['overrides'], **updates}
        connection.execute('UPDATE run_budgets SET version=version+1,overrides_json=?,updated_at=? WHERE run_id=?',
                           (canonical(overrides), now(), run_id))
        after = view(store, connection, run, defaults)
        connection.execute('INSERT INTO budget_actions VALUES(?,?,?,?,?,?,?,?)',
                           (run_id, request.action_id, digest(payload), canonical(before), canonical(after), actor, request.note, now()))
        store.event(connection, run_id, 'budget.increased_by_user',
                    {'actor': actor, 'action_id': request.action_id, 'note': request.note,
                     'before': {key: before[key] for key in KEYS}, 'after': {key: after[key] for key in KEYS},
                     'request_count_preserved': run['request_count'], 'approval_preserved': True,
                     'request_limit_action': 'NEW_CONFIRMED_LIMIT_HISTORY_UNKNOWN' if before['baseline_unknown'] else 'INCREASE_KNOWN_LIMIT',
                     'execution': 'NOT_STARTED', 'teacher_review': 'NOT_PERFORMED'})
        return after


def import_legacy_requests(store, run_id, state_path, expected_sha256, workspace, *, actor='local_user'):
    """Explicit local migration from preserved benchmark evidence; never execute a job.

    Only the historical request limit is imported. No HTTP endpoint accepts a
    filesystem path. Callers must supply the independently recorded evidence SHA.
    """
    if actor != 'local_user':
        raise AgentError('EXPLICIT_USER_BUDGET_REQUIRED', '历史预算迁移需要明确本地用户授权', 403)
    path = Path(state_path).resolve()
    try:
        raw = path.read_bytes()
        if digest(raw) != expected_sha256:
            raise ValueError('Evidence SHA mismatch')
        state = json.loads(raw)
        if Path(state['workspace']).resolve() != Path(workspace).resolve():
            raise ValueError('Evidence workspace mismatch')
        matches = [(name, case) for name, case in state['cases'].items() if case.get('run_id') == run_id]
        if len(matches) != 1:
            raise ValueError('Evidence must identify exactly one run')
        name, case = matches[0]
        limit = case['effective_request_limit']
        validate_defaults({'requests': limit})
        metrics = case['request_metrics']
        if type(metrics['request_limit']) is not int or metrics['request_limit'] != limit:
            raise ValueError('Evidence limit disagreement')
        count = case['request_count']
        if type(count) is not int or type(metrics['request_count']) is not int or count < 0 or metrics['request_count'] != count:
            raise ValueError('Evidence count disagreement')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise AgentError('BUDGET_EVIDENCE_INVALID', '历史预算证据的哈希、工作区、任务或计数校验失败', 409) from error
    with store.transaction() as connection:
        run = store.row(connection, run_id)
        if run['request_count'] != count:
            raise AgentError('BUDGET_EVIDENCE_STALE', '历史记录的请求计数与数据库不同，不能推断或覆盖', 409)
        if connection.execute("SELECT 1 FROM jobs WHERE run_id=? AND status IN ('queued','running')", (run_id,)).fetchone():
            raise AgentError('BUDGET_JOB_ACTIVE', '停止活动任务后才能核验导入历史预算', 409)
        existing = connection.execute('SELECT * FROM run_budgets WHERE run_id=?', (run_id,)).fetchone()
        if existing and 'requests' in json.loads(existing['defaults_json']):
            raise AgentError('BUDGET_ALREADY_INITIALIZED', '该任务已有请求预算基线，历史导入不能覆盖', 409)
        result = initialize_in_transaction(store, connection, run, {'requests': limit},
            'VERIFIED_BENCHMARK_STATE', verified_legacy=True)
        store.event(connection, run_id, 'budget.legacy_requests_imported', {
            'actor': actor, 'evidence_path': str(path), 'evidence_sha256': expected_sha256,
            'workspace': str(Path(workspace).resolve()), 'case': name, 'run_id': run_id,
            'requests': limit, 'request_count_preserved': count, 'historical_limit_inferred': False,
            'local_global_historical_limits': 'UNKNOWN', 'execution': 'NOT_STARTED'})
        return result
