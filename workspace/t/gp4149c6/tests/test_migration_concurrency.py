"""No model API: bounded bootstrap contention and actual independent processes."""
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from math_agent.store import Store
import math_agent.store as store_module

MIGRATION_COUNT = len(list(Path(store_module.__file__).with_name('migrations').glob('*.sql')))


@pytest.mark.parametrize('phase',['wal','migration_record'])
def test_transient_wal_busy_retries_whole_bootstrap_without_skipping_migration(tmp_path,monkeypatch,phase):
    original=Store.connect;calls={'busy':0,'closed':0}
    class BusyOnce:
        def __init__(self,connection):self.connection=connection
        def execute(self,sql,*args):
            target=(sql=='PRAGMA journal_mode=WAL' if phase=='wal' else sql.startswith('INSERT INTO schema_migrations VALUES'))
            if target and calls['busy']==0:
                calls['busy']+=1
                error=sqlite3.OperationalError('database is locked');error.sqlite_errorcode=sqlite3.SQLITE_BUSY
                raise error
            return self.connection.execute(sql,*args)
        def __getattr__(self,name):return getattr(self.connection,name)
        def __enter__(self):self.connection.__enter__();return self
        def __exit__(self,*args):return self.connection.__exit__(*args)
        def close(self):calls['closed']+=1;self.connection.close()
    monkeypatch.setattr(Store,'connect',lambda self:BusyOnce(original(self)))
    store=Store(tmp_path/'agent.db')
    with store.connect() as c:
        assert c.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0]==MIGRATION_COUNT
    assert calls['busy']==1 and calls['closed']>=2


def test_bootstrap_lock_timeout_is_bounded_and_retry_after_unlock_recovers(tmp_path,monkeypatch):
    import math_agent.store as module
    path=tmp_path/'locked.db';Store(path)
    holder=sqlite3.connect(path,isolation_level=None)
    holder.execute('BEGIN IMMEDIATE')
    monkeypatch.setattr(module,'MIGRATION_LOCK_TIMEOUT_SECONDS',0.25,raising=False)
    started=time.monotonic()
    try:
        with pytest.raises(sqlite3.OperationalError,match='locked'):Store(path)
        assert time.monotonic()-started<1.5
    finally:
        holder.rollback();holder.close()
    recovered=Store(path)
    with recovered.connect() as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0]==MIGRATION_COUNT


def test_non_lock_sql_error_is_not_hidden_or_retried(tmp_path,monkeypatch):
    calls=[];original=Store.connect
    class Broken:
        def __init__(self,c):self.c=c
        def __getattr__(self,name):return getattr(self.c,name)
        def execute(self,sql,*args):
            if sql=='PRAGMA journal_mode=WAL':calls.append(sql);raise sqlite3.OperationalError('synthetic non-lock SQL failure')
            return self.c.execute(sql,*args)
        def __enter__(self):return self
        def __exit__(self,*args):self.c.close()
    monkeypatch.setattr(Store,'connect',lambda self:Broken(original(self)))
    with pytest.raises(sqlite3.OperationalError,match='non-lock'):Store(tmp_path/'broken.db')
    assert len(calls)==1


@pytest.mark.integration
def test_repeated_simultaneous_threads_keep_wal_and_single_migration(tmp_path):
    for round_number in range(12):
        path=tmp_path/f'round-{round_number}.db';barrier=threading.Barrier(8)
        def start(_):barrier.wait(timeout=5);return Store(path)
        with ThreadPoolExecutor(8) as pool:stores=list(pool.map(start,range(8)))
        with stores[0].connect() as c:
            assert c.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
            assert c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0]==MIGRATION_COUNT
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


@pytest.mark.integration
def test_separate_processes_can_start_against_same_new_database(tmp_path):
    path=tmp_path/'shared.db';gate=tmp_path/'start'
    code="""import json,sys,time
from pathlib import Path
from math_agent.store import Store
gate=Path(sys.argv[2]);deadline=time.monotonic()+10
while not gate.exists():
    if time.monotonic()>deadline:raise RuntimeError('start gate timeout')
    time.sleep(.01)
for _ in range(5):store=Store(Path(sys.argv[1]))
with store.connect() as c:print(json.dumps({'wal':c.execute('PRAGMA journal_mode').fetchone()[0],'versions':c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],'integrity':c.execute('PRAGMA integrity_check').fetchone()[0]}))
"""
    allow={'SYSTEMROOT','WINDIR','COMSPEC','PATH','TEMP','TMP','PATHEXT','SYSTEMDRIVE'}
    env={k:v for k,v in os.environ.items() if k.upper() in allow}
    env.update(MATH_AGENT_API_KEY='',MATH_AGENT_LIVE_API_ENABLED='false',MATH_AGENT_LLM_STREAMING='false')
    processes=[subprocess.Popen([sys.executable,'-c',code,str(path),str(gate)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) for _ in range(4)]
    try:
        gate.write_bytes(b'go')
        for process in processes:
            out,err=process.communicate(timeout=25)
            assert process.returncode==0,err
            assert json.loads(out)=={'wal':'wal','versions':MIGRATION_COUNT,'integrity':'ok'}
    finally:
        for process in processes:
            if process.poll() is None:process.kill();process.wait(timeout=5)
