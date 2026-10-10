"""Set Windows user environment variables without keys in files or command arguments."""
import ctypes
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from uuid import uuid4


def environment_values(provider, secret, streaming=False):
    """Return only the selected provider's variables; do not rewrite other keys."""
    if provider == 'deepseek':
        return {'MATH_AGENT_DEEPSEEK_API_KEY': secret,
                'MATH_AGENT_DEEPSEEK_API_BASE_URL': 'https://api.deepseek.com'}
    return {'MATH_AGENT_API_KEY': secret, 'MATH_AGENT_LIVE_API_ENABLED': 'true',
            'MATH_AGENT_API_BASE_URL': 'https://oneapi.advancedsolver.com/v1',
            'MATH_AGENT_MODEL': 'gpt-6-astra', 'MATH_AGENT_LLM_STREAMING': str(streaming).lower()}


def read_secret(from_stdin=False):
    if from_stdin:
        # Explicit pipe mode for automation. Never accept a key in argv or a file.
        if sys.stdin.isatty():
            raise SystemExit('--key-stdin requires a redirected pipe; use hidden input in a terminal.')
        secret = sys.stdin.readline(4097).rstrip('\r\n')
    else:
        secret = getpass.getpass('API key (hidden input; saved only as Windows user environment variable): ')
    if not 16 <= len(secret) <= 4096 or any(c.isspace() for c in secret):
        raise SystemExit('Invalid key shape; no environment changes were made.')
    return secret

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['gpt6', 'deepseek'], default='gpt6')
    parser.add_argument('--key-stdin', action='store_true', help='Read one key from a redirected stdin pipe; never put it in argv')
    parser.add_argument('--streaming',action='store_true',help='Enable SSE after confirming provider streaming support')
    args=parser.parse_args()
    if os.name!='nt':
        raise SystemExit('Windows user environment configuration only.')
    import winreg
    if args.provider == 'deepseek' and args.streaming:
        parser.error('DeepSeek profiles use stream=false; --streaming applies only to gpt6.')
    secret=read_secret(args.key_stdin)
    values=environment_values(args.provider, secret, args.streaming)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,'Environment',0,winreg.KEY_SET_VALUE) as key:
        for name,value in values.items():
            winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
            os.environ[name]=value
    # Notify future desktop-launched processes; already running workers need restart.
    result=ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF,0x001A,0,'Environment',2,2000,ctypes.byref(result))
    evidence={'timestamp':datetime.now(timezone.utc).isoformat(),'scope':'Windows current-user environment',
              'provider':args.provider, 'key_configured':True,'key_value':'NOT_RECORDED',
              'variables_written':list(values), 'other_provider_variables':'UNCHANGED',
              'base_url':values.get('MATH_AGENT_DEEPSEEK_API_BASE_URL', values.get('MATH_AGENT_API_BASE_URL')),
              'models':['deepseek-flash','deepseek-v4-pro'] if args.provider=='deepseek' else ['gpt-6-astra'],
              'streaming_enabled':False if args.provider=='deepseek' else args.streaming,
              'thinking':{'type':'enabled'} if args.provider=='deepseek' else None,
              'reasoning_effort':'high' if args.provider=='deepseek' else None,
              'live_enabled_changed':args.provider=='gpt6',
              'service_restart_required':True,'real_api_test':'NOT_RUN'}
    destination=Path(__file__).resolve().parents[1]/'reports'/'iteration3'
    destination.mkdir(parents=True,exist_ok=True)
    report=destination/('environment-'+args.provider+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8]+'.json')
    with report.open('x', encoding='utf-8') as handle:
        json.dump(evidence, handle, ensure_ascii=False, indent=2)
    evidence['report']=str(report)
    print(json.dumps(evidence,ensure_ascii=True))
    secret=None
    return 0

if __name__=='__main__':
    raise SystemExit(main())
