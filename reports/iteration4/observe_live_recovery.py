"""Read-only compact progress plus preserved full event tails for two live jobs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[2]
database = ROOT/'workspace/iteration2-live/agent.db'
result = {'at': datetime.now(timezone.utc).isoformat(), 'read_only': True, 'cases': {}}
with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
    connection.row_factory = sqlite3.Row
    for name, run_id in [('CH01','05748ab6260c40989a560a98e1e2065a'), ('CH02','fd6736af6ef14be3839e019e86ca1e5c'), ('CH03','a45be503af594ce8aae0bb1e4c30184b')]:
        row = dict(connection.execute('SELECT id,status,stage,request_count,error_json FROM runs WHERE id=?', (run_id,)).fetchone())
        row['error'] = json.loads(row.pop('error_json') or 'null')
        row['events'] = []
        for event in reversed(connection.execute('SELECT sequence,type,payload_json,timestamp FROM events WHERE run_id=? ORDER BY sequence DESC LIMIT 16', (run_id,)).fetchall()):
            item = dict(event); item['payload'] = json.loads(item.pop('payload_json')); row['events'].append(item)
        result['cases'][name] = row
folder = ROOT/'reports/iteration4/live-recovery-observations'; folder.mkdir(exist_ok=True)
target = folder/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.json')
target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
compact = {}
for name, row in result['cases'].items():
    compact[name] = {key:value for key,value in row.items() if key!='events'}
    compact[name]['events'] = [{**{key:item[key] for key in ('sequence','type','timestamp')},
        'payload': {key:value for key,value in item['payload'].items()
            if key in ('role','model_id','code','message','section_id','status','unit_ids','http_status','provider_calls_during_replay')}}
        for item in row['events'][-10:]]
print(json.dumps({'report':str(target),'cases':compact}, ensure_ascii=False))
