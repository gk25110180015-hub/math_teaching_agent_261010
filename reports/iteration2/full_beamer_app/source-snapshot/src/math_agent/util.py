import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    if not isinstance(value, bytes):
        value = (value if isinstance(value, str) else canonical(value)).encode('utf-8')
    return hashlib.sha256(value).hexdigest()


def scrub(value):
    text = str(value)
    secret = os.environ.get('MATH_AGENT_API_KEY', '')
    if secret:
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)bearer\s+[^\s"\'<>]+', 'Bearer [REDACTED]', text)
    text = re.sub(r'sk-[A-Za-z0-9_\-]{8,}', '[REDACTED]', text)
    text = re.sub(r'(?i)(api[_-]?key["\s:=]+)[^\s,"}]+', r'\1[REDACTED]', text)
    return text.replace('\x1b', '').replace('\x00', '')


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # A short sibling name avoids Windows MAX_PATH failures in Chinese workspaces.
    temporary = path.with_name('.' + uid()[:12] + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def within(root: Path, key: str):
    p = (root / key).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError('路径越界')
    return p


class AgentError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, scrub(message), status
