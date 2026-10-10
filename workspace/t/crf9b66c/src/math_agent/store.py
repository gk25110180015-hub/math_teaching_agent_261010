"""Durable SQLite repository. No network/compilation occurs inside transactions."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from .util import AgentError, canonical, digest, now, uid


MIGRATION_LOCK_TIMEOUT_SECONDS = 20.0


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self):
        c = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=20000')
        return c

    def migrate(self):
        # journal_mode can return SQLITE_BUSY immediately when two fresh
        # connections negotiate WAL, despite the ordinary busy timeout. Retry
        # that bootstrap using fresh connections, with one total deadline.
        deadline=time.monotonic()+MIGRATION_LOCK_TIMEOUT_SECONDS
        while True:
            c=None
            try:
                c=self.connect()
                def bounded_wait():
                    remaining=max(0,deadline-time.monotonic())
                    c.execute('PRAGMA busy_timeout='+str(max(1,min(250,int(remaining*1000)))))
                bounded_wait()
                if c.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower()!='wal':
                    raise sqlite3.OperationalError('WAL journal mode is unavailable; migration was not performed')
                bounded_wait()
                c.execute('BEGIN IMMEDIATE')
                c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
                for file in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
                    version = int(file.stem.split('_')[0])
                    if not c.execute('SELECT 1 FROM schema_migrations WHERE version=?', (version,)).fetchone():
                        for statement in file.read_text(encoding='utf-8').split(';'):
                            if statement.strip():
                                c.execute(statement)
                        c.execute('INSERT INTO schema_migrations VALUES(?,?)',(version,now()))
                c.commit()
                return
            except sqlite3.OperationalError as exc:
                code=getattr(exc,'sqlite_errorcode',None)
                is_busy=((code & 255) in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)) if code is not None else str(exc).lower() in {
                    'database is locked','database table is locked','database schema is locked','database is busy'}
                if not is_busy or time.monotonic()>=deadline:
                    raise
            finally:
                if c is not None:
                    try:
                        if c.in_transaction:c.rollback()
                    finally:c.close()
            time.sleep(min(0.05,max(0,deadline-time.monotonic())))

    @contextmanager
    def transaction(self):
        c = self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def event(self, c, run_id, kind, payload=None):
        c.execute('INSERT INTO events(run_id,type,payload_json,timestamp) VALUES(?,?,?,?)',
                  (run_id, kind, canonical(payload or {}), now()))

    def row(self, c, run_id):
        row = c.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise AgentError('NOT_FOUND', '任务不存在', 404)
        return dict(row)

    def current_plan(self, c, run):
        if run['active_plan_revision'] is None:
            return None
        row = c.execute('SELECT * FROM plans WHERE run_id=? AND revision=?',
                        (run['id'], run['active_plan_revision'])).fetchone()
        plan = json.loads(row['canonical_json'])
        return {**plan, 'hash': row['hash']}

    def save_plan(self, c, run_id, plan):
        run = self.row(c, run_id)
        revision = (run['active_plan_revision'] or 0) + 1
        plan = {**plan, 'revision': revision}
        plan.pop('hash', None)
        encoded = canonical(plan)
        hash_ = digest(encoded)
        c.execute('INSERT INTO plans VALUES(?,?,?,?,?,?,?)',
                  (run_id, revision, hash_, encoded, run['active_plan_revision'], 'draft', now()))
        status = 'AWAITING_PLAN_INPUT' if plan.get('unresolved_blocking_questions') else 'PLAN_READY'
        c.execute('UPDATE runs SET active_plan_revision=?,status=?,stage=?,updated_at=? WHERE id=?',
                  (revision, status, 'plan.input' if status == 'AWAITING_PLAN_INPUT' else 'plan.ready', now(), run_id))
        self.event(c, run_id, 'plan.revised', {'revision': revision, 'hash': hash_})
        return {**plan, 'hash': hash_}

    def get_run(self, run_id):
        with self.connect() as c:
            run = self.row(c, run_id)
            run['input'] = json.loads(run.pop('input_json'))
            run['error'] = json.loads(run.pop('error_json') or 'null')
            run['plan'] = self.current_plan(c, run)
            a = c.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?', (run_id, run['active_plan_revision'])).fetchone()
            run['approval'] = dict(a) if a else None
            run['jobs'] = [dict(r) for r in c.execute('SELECT id,kind,status,attempt,fencing_token FROM jobs WHERE run_id=? ORDER BY created_at', (run_id,))]
            run['artifacts'] = self.artifacts(run_id, c)
            run['reviews'] = [dict(r) for r in c.execute('SELECT * FROM reviews WHERE run_id=?', (run_id,))]
            return run

    def artifacts(self, run_id, c=None):
        if c is None:
            with self.connect() as conn:
                return self.artifacts(run_id, conn)
        out = []
        for r in c.execute('SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at,name', (run_id,)):
            a = dict(r)
            a['metadata'] = json.loads(a.pop('metadata_json'))
            a.pop('storage_key')
            out.append(a)
        return out

    def claim(self, owner, lease_seconds=60):
        with self.transaction() as c:
            row = c.execute("SELECT j.* FROM jobs j JOIN runs r ON r.id=j.run_id WHERE (j.status='queued' OR (j.status='running' AND j.lease_deadline<?)) AND r.status!='CANCELLED' ORDER BY j.created_at LIMIT 1", (time.time(),)).fetchone()
            if not row:
                return None
            job = dict(row)
            job.update(lease_owner=owner, lease_deadline=time.time() + lease_seconds, fencing_token=job['fencing_token'] + 1, attempt=job['attempt'] + 1, status='running')
            c.execute("UPDATE jobs SET status='running',lease_owner=?,lease_deadline=?,fencing_token=?,attempt=? WHERE id=?",
                      (owner, job['lease_deadline'], job['fencing_token'], job['attempt'], job['id']))
            self.event(c, job['run_id'], 'job.claimed', {'job_id': job['id'], 'attempt': job['attempt'], 'recovered': row['status'] == 'running'})
            return job

    def assert_fence(self, c, job):
        row = c.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone()
        run = self.row(c, job['run_id'])
        if not row or row['fencing_token'] != job['fencing_token'] or row['lease_owner'] != job['lease_owner'] or row['status'] != 'running' or row['lease_deadline'] < time.time() or run['status'] == 'CANCELLED':
            raise AgentError('LEASE_LOST', '任务已取消或租约已交给另一 worker；旧结果不提交', 409)

    def heartbeat(self, owner, job=None, lease_seconds=60):
        with self.transaction() as c:
            c.execute('INSERT OR REPLACE INTO worker_heartbeats VALUES(?,?)', (owner, time.time()))
            if job:
                self.assert_fence(c, job)
                c.execute('UPDATE jobs SET lease_deadline=? WHERE id=?', (time.time() + lease_seconds, job['id']))

    def active(self, job):
        try:
            with self.connect() as c:
                self.assert_fence(c, job)
            return True
        except AgentError:
            return False

    def stage(self, job, status, stage):
        with self.transaction() as c:
            self.assert_fence(c, job)
            c.execute('UPDATE runs SET status=?,stage=?,updated_at=? WHERE id=?', (status, stage, now(), job['run_id']))
            self.event(c, job['run_id'], 'stage', {'status': status, 'stage': stage})

    def checkpoint(self, job, step_key, input_hash, output):
        with self.transaction() as c:
            self.assert_fence(c, job)
            c.execute('INSERT OR REPLACE INTO steps VALUES(?,?,?,?,?,?)', (job['run_id'], step_key, input_hash, canonical(output), digest(output), now()))
            self.event(c, job['run_id'], 'step.checkpoint', {'step_key': step_key, 'output_hash': digest(output)})

    def cached_step(self, run_id, step_key, input_hash):
        with self.connect() as c:
            row = c.execute('SELECT * FROM steps WHERE run_id=? AND step_key=? AND input_hash=?', (run_id, step_key, input_hash)).fetchone()
            if row:
                value = json.loads(row['output_json'])
                if digest(value) == row['output_hash']:
                    return value
        return None

    def count_request(self, job, limit, metadata, hard_limit=None):
        if hard_limit is not None and (type(hard_limit) is not int or not 0 <= hard_limit <= 1000):
            raise ValueError('Caller request hard cap must be a bounded integer')
        # Persist the actual initial limit even when this very call is exhausted.
        self.initialize_budget(job, {'requests': limit})
        with self.transaction() as c:
            self.assert_fence(c, job)
            run = self.row(c, job['run_id'])
            from .budget import view
            budget = view(self, c, run)
            effective = budget['requests'] if hard_limit is None else min(budget['requests'], hard_limit)
            if run['request_count'] >= effective:
                raise AgentError('BUDGET_EXHAUSTED', f"模型请求预算已用尽：已用 {run['request_count']}，任务上限 {budget['requests']}，调用者额外上限 {hard_limit if hard_limit is not None else '无'}；已完成章节和审批已保留")
            c.execute('UPDATE runs SET request_count=request_count+1 WHERE id=?', (job['run_id'],))
            self.event(c, job['run_id'], 'provider.request', metadata)

    def initialize_budget(self, job, defaults):
        from .budget import initialize_in_transaction
        with self.transaction() as c:
            self.assert_fence(c, job)
            run = self.row(c, job['run_id'])
            return initialize_in_transaction(self, c, run, defaults,
                'ACTUAL_EXECUTION_SETTINGS_LEGACY' if run['request_count'] else 'ACTUAL_EXECUTION_SETTINGS')

    def effective_budget(self, run_id, defaults=None):
        from .budget import view
        with self.connect() as c:
            return view(self, c, self.row(c, run_id), defaults)

    def finish(self, job, status, stage, error=None):
        with self.transaction() as c:
            self.assert_fence(c, job)
            if error and error.get('code') == 'BUDGET_EXHAUSTED':
                from .budget import view
                budget = view(self, c, self.row(c, job['run_id']))
                error = {**error, 'budget_version': budget['version']}
            c.execute('UPDATE runs SET status=?,stage=?,error_json=?,updated_at=? WHERE id=?', (status, stage, canonical(error) if error else None, now(), job['run_id']))
            c.execute('UPDATE jobs SET status=?,lease_deadline=NULL,error_json=? WHERE id=?',
                      ('failed' if status in ('FAILED', 'BLOCKED') else 'done', canonical(error) if error else None, job['id']))
            self.event(c, job['run_id'], 'job.finished', {'status': status, 'stage': stage, 'error': error})

    def publish_artifacts(self, job, artifacts):
        with self.transaction() as c:
            self.assert_fence(c, job)
            revision = self.row(c, job['run_id'])['active_plan_revision'] or 0
            for a in artifacts:
                c.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (uid(), job['run_id'], revision, a['storage_key'], a['name'], a['sha256'], a['media_type'], 'draft', canonical(a.get('metadata', {})), now()))
