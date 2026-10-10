"""Read-only restart preflight/postflight; no vendor calls or task mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def snapshot():
    result={'timestamp':datetime.now(timezone.utc).isoformat(),'instances':[], 'model_api_calls':0}
    for name,port in [('workspace',8765),('workspace/iteration2-live',8766)]:
        workspace=ROOT/name
        con=sqlite3.connect((workspace/'agent.db').as_uri()+'?mode=ro',uri=True)
        con.row_factory=sqlite3.Row
        try:
            names={row['name'] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            tables={}
            for table in ['runs','jobs','approvals','plans','steps','artifacts','reviews','run_budgets','budget_actions']:
                if table not in names:continue
                rows=[dict(row) for row in con.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                tables[table]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
            active=con.execute("SELECT COUNT(*) FROM jobs WHERE lower(status) IN ('queued','running')").fetchone()[0]
            runs=[dict(row) for row in con.execute('SELECT id,status,stage,request_count FROM runs ORDER BY id')]
        finally:con.close()
        def get(path):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=10) as response:
                return json.load(response)
        health=get('/api/health');caps=get('/api/capabilities')
        result['instances'].append({'workspace':str(workspace),'port':port,'active_jobs':active,
            'tables':tables,'runs':runs,'health':health,'public_settings':caps['settings']})
    result['safe_to_restart']=all(entry['active_jobs']==0 for entry in result['instances'])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compare',type=Path)
    args=parser.parse_args()
    destination=args.output.resolve()
    if not destination.is_relative_to((ROOT/'reports').resolve()) or destination.exists():
        parser.error('Choose a new report path.')
    data=snapshot()
    if args.compare:
        before=json.loads(args.compare.read_text(encoding='utf-8'))
        data['task_tables_unchanged']=all(old['tables']==new['tables'] for old,new in zip(before['instances'],data['instances']))
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(destination),'safe_to_restart':data['safe_to_restart'],
        'task_tables_unchanged':data.get('task_tables_unchanged'),'instances':[
            {'port':item['port'],'health':item['health'],'active_jobs':item['active_jobs'],
             'model_ids':[model['id'] for model in item['public_settings'].get('models',[])]}
            for item in data['instances']]},ensure_ascii=True))
    return 0 if data['safe_to_restart'] and data.get('task_tables_unchanged',True) else 2


if __name__=='__main__':
    raise SystemExit(main())
