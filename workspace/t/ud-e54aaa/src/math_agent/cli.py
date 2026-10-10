import argparse
import json
import os
import platform
import subprocess
from pathlib import Path
from uuid import uuid4
from .settings import Settings, PROJECT_ROOT
from .model_routing import MODEL_IDS
from .util import AgentError, now, scrub, write_json


def provider_capability_check(settings, requested_model='gpt6', allow_fallback=True, *, report_root=None):
    """A real text probe, preserving failures and attributing success to its model."""
    from .provider import CompatibleChatProvider
    report_root = Path(report_root) if report_root is not None else PROJECT_ROOT / 'reports'
    records = []
    evidence = {'timestamp': now(), 'test_kind': 'REAL_API_TEXT_PROBE',
                'requested_model_id': requested_model, 'fallback_enabled': allow_fallback,
                'actual_model_id': None, 'text': 'untested', 'vision': 'untested',
                'tools': 'untested', 'json_schema': 'untested', 'streaming': 'untested',
                'price': None, 'human_visual_review': 'NOT_RUN'}
    result = None
    try:
        result = CompatibleChatProvider(settings, record=records.append,
                    preferred_model=requested_model, allow_fallback=allow_fallback).check()
        completed = [r for r in records if r.get('transport_status') == 'SUCCESS']
        if not completed:
            raise AgentError('PROBE_IDENTITY_UNKNOWN', '连通检查缺少成功请求的模型身份，不能标记模型可用。')
        actual = completed[-1]['model_id']
        profile = settings.model_profile(actual)
        evidence.update({'status': 'PASS', 'actual_model_id': actual, 'id': actual,
                         'model': profile['model'], 'base_url': profile['base_url'],
                         'streaming_enabled': profile['streaming'], 'thinking': profile['thinking'],
                         'reasoning_effort': profile['reasoning_effort'], 'text': 'supported',
                         'tested': {'requested': requested_model, 'actual': actual},
                         'reported_model': completed[-1].get('reported_model'),
                         'streaming': 'supported' if completed[-1].get('stream_complete') else 'untested',
                         'response': result[:100], 'usage': completed[-1].get('usage')})
        exit_code = 0
    except AgentError as exc:
        evidence.update({'status': 'BLOCKED', 'code': exc.code, 'message': exc.message, 'usage': None})
        exit_code = 2
    evidence['request_records'] = records
    evidence['request_count'] = len({r['call_id'] for r in records if r.get('call_id')})
    secrets = (settings.api_key.get_secret_value(), settings.deepseek_api_key.get_secret_value())
    def redact(value):
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return scrub(value, secrets=secrets) if isinstance(value, str) else value
    evidence = redact(evidence)
    report = report_root / 'iteration3' / ('capability-' + requested_model + '-' + uuid4().hex + '.json')
    evidence['report'] = str(report)
    write_json(report, evidence)
    if evidence['status'] == 'PASS':
        # Per-model latest capability is the only intentional overwrite. Every
        # invocation, including failure, also has its immutable unique report.
        write_json(report_root / 'model-capabilities' / (evidence['actual_model_id'] + '.json'), evidence)
    return evidence, exit_code


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
    provider.add_argument('--model', choices=list(MODEL_IDS), default='gpt6')
    provider.add_argument('--no-fallback', action='store_true', help='Check only the selected model; do not attribute a fallback success to it')
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
            evidence, exit_code=provider_capability_check(settings, args.model, not args.no_fallback)
            print(json.dumps(evidence,ensure_ascii=False))
            return exit_code
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
