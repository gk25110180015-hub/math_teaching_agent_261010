"""Check that the configured credential was not written to project artifacts."""
import json
import os
import argparse
from pathlib import Path
from math_agent.settings import Settings, PROJECT_ROOT
from math_agent.util import now, write_json

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=PROJECT_ROOT/'reports/iteration2/secret_storage_audit.json')
args=parser.parse_args()
output=args.output.resolve()
if not output.is_relative_to((PROJECT_ROOT/'reports').resolve()):
    parser.error('--output must be within project reports')
if output.exists():
    parser.error('Output already exists; use a new report path to preserve earlier evidence')
settings=Settings()
configured_credentials={'gpt6':settings.api_key.get_secret_value(),
                        'deepseek':settings.deepseek_api_key.get_secret_value()}
configured_credentials={name:value for name,value in configured_credentials.items() if value}
if not configured_credentials:
    raise SystemExit('Environment credential is required for this local check; no value is printed.')
needles=[secret.encode(encoding) for secret in configured_credentials.values()
         for encoding in ('utf-8','utf-16-le','utf-16-be')]
checked=0
matches=[]
unreadable=[]
extensions={'.py','.ps1','.md','.txt','.json','.jsonl','.log','.xml','.tex','.sty','.yaml','.yml','.toml','.html','.js','.css','.db','.db-wal','.db-shm','.sqlite','.sqlite3','.sqlite-wal','.sqlite3-wal','.env'}
for directory,dirs,files in os.walk(PROJECT_ROOT,onerror=lambda error:unreadable.append(str(error.filename))):
    dirs[:]=[d for d in dirs if d not in {'.venv','.git','__pycache__','.pytest_cache','node_modules'}]
    for name in files:
        path=Path(directory)/name
        if path.suffix.lower() not in extensions and not name.lower().startswith('.env.'):
            continue
        tail=b''
        try:
            with path.open('rb') as stream:
                while chunk:=stream.read(1024*1024):
                    data=tail+chunk
                    if any(needle in data for needle in needles):
                        matches.append(str(path.relative_to(PROJECT_ROOT)))
                        break
                    tail=data[-max(map(len,needles)):]
            checked+=1
        except OSError:
            unreadable.append(str(path))
report={'created_at':now(),'status':'FAIL' if matches else 'INCOMPLETE' if unreadable else 'PASS','files_checked':checked,
    'matching_file_paths':matches,'credential_value':'NOT_RECORDED',
    'configured_credential_profiles':list(configured_credentials),
    'unreadable_paths':unreadable,
    'extensions':sorted(extensions),'additional_names':'.env.*','encodings':['utf-8','utf-16-le','utf-16-be'],
    'scope':'Exact currently configured credentials in selected project source/text/report/TeX/SQLite/WAL/SHM/environment-file bytes at scan time; virtualenv/git/cache and compressed artifacts excluded. No model requests.'}
write_json(output,report)
print(json.dumps(report,ensure_ascii=True))
