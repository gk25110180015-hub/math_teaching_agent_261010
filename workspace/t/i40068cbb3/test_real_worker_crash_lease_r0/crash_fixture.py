import sys,time
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
