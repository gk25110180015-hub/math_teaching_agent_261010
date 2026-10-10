"""Isolated candidate validation; never imports user API settings or uses WAN."""
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = Path(__file__).resolve().parent
for name in list(os.environ):
    if name.startswith('MATH_AGENT_') or name == 'OPENAI_API_KEY':
        del os.environ[name]
attempts = []
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex
original_getaddrinfo = socket.getaddrinfo


def local(address):
    if not isinstance(address, tuple):
        return True
    try:
        return ipaddress.ip_address(address[0]).is_loopback
    except ValueError:
        return address[0] == 'localhost'


def connect(self, address):
    if not local(address):
        attempts.append('connect')
        raise AssertionError('External socket access forbidden in offline candidate tests')
    return original_connect(self, address)


def connect_ex(self, address):
    if not local(address):
        attempts.append('connect_ex')
        raise AssertionError('External socket access forbidden in offline candidate tests')
    return original_connect_ex(self, address)


def getaddrinfo(host, port, *args, **kwargs):
    if not local((host, port)):
        attempts.append('getaddrinfo')
        raise AssertionError('External DNS access forbidden in offline candidate tests')
    return original_getaddrinfo(host, port, *args, **kwargs)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = getaddrinfo
validation = BUNDLE/'validation'
package = validation/'package/math_agent'
for name in ('uncertainty_review.py', 'uncertainty_protocol_recovery.py', 'provider.py'):
    shutil.copyfile(BUNDLE/name, package/name)
sys.path.insert(0, str(ROOT/'tests'))
sys.path.insert(0, str(package.parent))
import math_agent
assert Path(math_agent.__file__).is_relative_to(package)
import pytest
version = sys.argv[1] if len(sys.argv)>1 else 'offline'
code = pytest.main(['-c', str(ROOT/'pyproject.toml'),
    str(BUNDLE/'test_uncertainty_protocol_recovery.py'), str(ROOT/'tests/test_uncertainty_review.py'),
    str(ROOT/'tests/test_model_routing.py'), str(ROOT/'tests/test_provider.py'),
    '-q', '-m', 'not real_api', '--basetemp='+str(ROOT/'workspace'/('upr-'+uuid.uuid4().hex[:6])),
    '--junitxml='+str(validation/(version+'.xml'))])
(validation/(version+'-runtime.json')).write_text(json.dumps({
    'pytest_exit': code, 'external_attempts': len(attempts), 'real_api': 'EXCLUDED',
    'api_keys': 'REMOVED_FROM_TEST_PROCESS', 'tested_package': str(package),
    'teacher_review': 'NOT_RUN'}, indent=2), encoding='utf-8')
raise SystemExit(code)
