"""Crash a real worker process using a synthetic step; no provider or teacher review."""
import os
import subprocess
import sys
import time
from pathlib import Path
import pytest
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.domain import NewRun
from math_agent.mathcheck import math_child_environment


@pytest.mark.integration
def test_real_worker_crash_lease_recovery_keeps_checkpoint(tmp_path):
    settings=Settings(workspace=tmp_path/'w',lease_seconds=5)
    service=Service(settings)
    run=service.create(NewRun(workflow_id='lecture.generate',topic='合成崩溃恢复fixture'))
    service.propose(run['id'])
    script=tmp_path/'crash_fixture.py'
    script.write_text('''import sys,time
from math_agent.settings import Settings
from math_agent.worker import Worker
import math_agent.worker as module
class SyntheticPipeline:
    def __init__(self,settings,store,job):
        self.store,self.job=store,job
        self.run=store.get_run(job['run_id'])
    def plan(self):
        self.store.stage(self.job,'BUILDING','synthetic.S02')
        self.store.checkpoint(self.job,'synthetic.S01','fixture-hash',{'retained':'completed-before-crash'})
        print('READY',flush=True)
        time.sleep(60)
module.Pipeline=SyntheticPipeline
Worker(Settings(workspace=sys.argv[1],lease_seconds=5)).tick()
''',encoding='utf-8')
    process=subprocess.Popen([sys.executable,str(script),str(settings.workspace)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             env=math_child_environment(),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            saved=service.store.cached_step(run['id'],'synthetic.S01','fixture-hash')
            if saved:break
            if process.poll() is not None:pytest.fail(process.stderr.read().decode('utf-8','replace'))
            time.sleep(.1)
        assert saved and saved['retained']=='completed-before-crash'
        process.terminate();process.wait(timeout=10)
        # Wait for an actual lease expiry, without changing the DB clock/deadline.
        time.sleep(5.2)
        replacement=Service(Settings(workspace=settings.workspace,lease_seconds=5))
        recovered=replacement.store.claim('replacement-process',5)
        assert recovered and recovered['attempt']==2 and recovered['fencing_token']==2
        assert replacement.store.cached_step(run['id'],'synthetic.S01','fixture-hash')==saved
        replacement.store.finish(recovered,'BLOCKED','synthetic.S02',{'code':'TEST_FIXTURE_STOP','message':'recovery verified; no human or API acceptance'})
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=10)
