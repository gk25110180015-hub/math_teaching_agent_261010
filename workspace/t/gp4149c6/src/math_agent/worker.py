import threading
import time
from .pipeline import Pipeline
from .store import Store
from .util import AgentError, digest, now, scrub, uid, write_json


class Worker:
    def __init__(self, settings):
        self.settings=settings
        self.store=Store(settings.db_path)
        self.owner=uid()
        self.stopping=False

    def tick(self):
        self.store.heartbeat(self.owner)
        job=self.store.claim(self.owner,self.settings.lease_seconds)
        if not job:
            return False
        done=threading.Event()
        def pulse():
            while not done.wait(min(5,self.settings.lease_seconds/3)):
                try:
                    self.store.heartbeat(self.owner,job,self.settings.lease_seconds)
                except AgentError:
                    return
        thread=threading.Thread(target=pulse,daemon=True)
        thread.start()
        try:
            pipeline=Pipeline(self.settings,self.store,job)
            from .workflows.registry import workflow
            plugin=workflow(pipeline.run['workflow_id'])
            plugin.propose_plan(pipeline.run['input'],pipeline) if job['kind']=='plan' else plugin.build_next_step(pipeline.run,pipeline)
        except Exception as exc:
            if self.store.active(job):
                error={'code':exc.code if isinstance(exc,AgentError) else type(exc).__name__,
                       'message':scrub(exc.message if isinstance(exc,AgentError) else str(exc))[:4000],
                       'timestamp':now(),'job_id':job['id'],'attempt':job['attempt'],
                       'recovery':'原审批和已通过章节保留；修复条件后点击重试。崩溃边界的外部调用可能重复计费。'}
                run=self.store.get_run(job['run_id'])
                diagnostic=self.settings.workspace/'runs'/job['run_id']/'errors'/(uid()[:12]+'.json')
                write_json(diagnostic,error)
                self.store.publish_artifacts(job,[{'storage_key':diagnostic.relative_to(self.settings.workspace).as_posix(),
                    'name':'failure_diagnostic.json','sha256':digest(diagnostic.read_bytes()),'media_type':'application/json',
                    'metadata':{'kind':'failure_diagnostic','attempt':job['attempt']}}])
                blocked=isinstance(exc,AgentError) and any(part in exc.code for part in ('BLOCKED','CONFIGURED','AUTH','BUDGET','UNAVAILABLE','TRUST','ISOLATION','MATH','REPAIR_SCOPE'))
                self.store.finish(job,'BLOCKED' if blocked else 'FAILED',run['stage'],error)
        finally:
            done.set()
            thread.join(timeout=2)
        return True

    def run(self, once=False):
        if once:
            self.tick()
            return
        try:
            while not self.stopping:
                if not self.tick():
                    time.sleep(1)
        except KeyboardInterrupt:
            self.stopping=True
