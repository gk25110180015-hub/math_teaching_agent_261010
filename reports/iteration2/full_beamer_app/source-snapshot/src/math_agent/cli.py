import argparse
import json
import os
import platform
import subprocess
from pathlib import Path
from .settings import Settings, PROJECT_ROOT
from .util import AgentError, now, write_json


def doctor(settings):
    from .compiler import resolve_xelatex, safe_child_env
    from .beamer import theme_status
    engine=resolve_xelatex(settings.xelatex_path,forbidden_roots=[settings.workspace])
    result={'timestamp':now(),'platform':platform.platform(),'python':platform.python_version(),
            'compiler':{'status':'NOT_INSTALLED' if engine is None else 'NOT_RUN'},
            'settings':settings.public(),'templates':theme_status(settings.reference_root)}
    if engine:
        target=settings.workspace/'doctor'; target.mkdir(parents=True,exist_ok=True)
        p=subprocess.run([str(engine),'--version'],capture_output=True,timeout=20,env=safe_child_env(engine,target))
        result['compiler']={'status':'PASS' if p.returncode==0 else 'FAIL','path':str(engine),'version':p.stdout.decode('utf-8','replace').splitlines()[0]}
    write_json(PROJECT_ROOT/'reports'/'doctor_latest.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


def main():
    parser=argparse.ArgumentParser(prog='math-agent')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('doctor')
    serve=commands.add_parser('serve'); serve.add_argument('--host',default='127.0.0.1',choices=['127.0.0.1']); serve.add_argument('--port',type=int,default=8765)
    worker=commands.add_parser('worker'); worker.add_argument('--concurrency',type=int,choices=[1],default=1); worker.add_argument('--once',action='store_true')
    provider=commands.add_parser('provider'); provider.add_argument('action',choices=['check']); provider.add_argument('--live',action='store_true')
    references=commands.add_parser('references'); references.add_argument('action',choices=['index']); references.add_argument('--root',type=Path)
    args=parser.parse_args(); settings=Settings()
    try:
        if args.command=='doctor': return doctor(settings)
        if args.command=='serve':
            import uvicorn
            from .web.app import create_app
            settings=Settings(host=args.host,port=args.port)
            uvicorn.run(create_app(settings),host=args.host,port=args.port,reload=False,access_log=False)
        elif args.command=='worker':
            from .worker import Worker
            Worker(settings).run(once=args.once)
        elif args.command=='provider':
            if not args.live:
                print('NOT_RUN: 真实连通测试必须使用 --live 且启用环境变量；默认不消耗额度。')
                return 0
            from .provider import CompatibleChatProvider
            records=[]
            result=CompatibleChatProvider(settings,record=records.append).check()
            usage=next((r['usage'] for r in reversed(records) if r.get('usage') is not None),None)
            streaming=any(r.get('stream_complete') for r in records)
            evidence={'timestamp':now(),'model':settings.model,'base_url':settings.api_base_url,'text':'supported','vision':'untested','tools':'untested','json_schema':'untested','streaming':'supported' if streaming else 'untested','response':result[:100],'usage':usage,'price':None}
            write_json(PROJECT_ROOT/'reports'/'capabilities.json',evidence)
            print(json.dumps(evidence,ensure_ascii=False))
        elif args.command=='references':
            script=PROJECT_ROOT/'scripts'/'audit_references.py'
            import sys
            command=[sys.executable,str(script)]
            # The bundled audit script preserves originals and targets the configured project parent.
            if args.root:
                command += ['--root',str(args.root)]
            return subprocess.run(command,cwd=PROJECT_ROOT).returncode
    except AgentError as exc:
        evidence={'status':'BLOCKED','code':exc.code,'message':exc.message,'timestamp':now()}
        write_json(PROJECT_ROOT/'reports'/'last_cli_failure.json',evidence)
        print(json.dumps(evidence,ensure_ascii=False))
        return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
