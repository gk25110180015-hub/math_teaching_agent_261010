"""Bounded, diagnostic-preserving native TeX compilation. This is NOT a sandbox."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import signal
import subprocess
import time
from typing import Callable

ALLOWED_ASSETS = {'.tex', '.sty', '.cls', '.bib', '.bst', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.svg', '.csv', '.dat', '.pgf', '.tikz', '.json', '.md', '.txt'}
AUX_SUFFIXES = ('.aux', '.toc', '.nav', '.snm', '.out')
MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 200 * 1024 * 1024


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _issue(rule_id: str, message: str, *, severity='blocking', **location) -> dict:
    return {'rule_id': rule_id, 'severity': severity, 'message': message,
            'location': location, 'resolution_status': 'open'}


def scrub(text: str) -> str:
    for key, value in os.environ.items():
        if value and len(value) >= 8 and any(s in key.upper() for s in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD')):
            text = text.replace(value, '[REDACTED]')
    text = re.sub(r'(?i)Bearer\s+[^\s"\'<>]+', 'Bearer [REDACTED]', text)
    return re.sub(r'\bsk-[A-Za-z0-9_-]{8,}', '[REDACTED]', text)


def resolve_xelatex(explicit: str | None = None, *, forbidden_roots=()) -> Path | None:
    """Search absolute PATH entries ourselves; Windows current-dir search is excluded."""
    forbidden = [Path(p).resolve() for p in forbidden_roots]
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_absolute():
            return None
        candidates = [candidate]
    else:
        candidates = [Path(p) / ('xelatex.exe' if os.name == 'nt' else 'xelatex')
                      for p in os.environ.get('PATH', '').split(os.pathsep)
                      if p and Path(p).is_absolute() and Path(p).resolve() != Path.cwd().resolve()]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and not any(_within(resolved, root) for root in forbidden):
            if os.name != 'nt' or resolved.suffix.lower() == '.exe':
                return resolved
    return None


def safe_child_env(engine: Path, build_dir: Path) -> dict[str, str]:
    """Allowlist only; never inherit API credentials or arbitrary TeX search paths."""
    env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR', 'SystemDrive', 'COMSPEC', 'PATHEXT', 'LANG') if k in os.environ}
    system_bin = str(Path(os.environ.get('SystemRoot', '/usr')) / ('System32' if os.name == 'nt' else 'bin'))
    env.update({
        'PATH': os.pathsep.join([str(engine.parent), system_bin]),
        'TEMP': str(build_dir / '.tmp'), 'TMP': str(build_dir / '.tmp'),
        'TMPDIR': str(build_dir / '.tmp'),
        'TEXMFHOME': str(build_dir / '.texmf' / 'home'),
        'TEXMFCONFIG': str(build_dir / '.texmf' / 'config'),
        'TEXMFVAR': str(build_dir / '.texmf' / 'var'),
        'TEXINPUTS': '.' + os.pathsep,
        'openin_any': 'p', 'openout_any': 'p', 'shell_escape': 'f',
        'max_print_line': '1000',
    })
    return env


def bounded_directory_size(directory: Path) -> int:
    """TeX may atomically rename/remove auxiliaries while this bounded scan runs."""
    total = 0
    for path in directory.rglob('*'):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            continue
    return total


def terminate_tree(process: subprocess.Popen) -> None:
    """Terminate only the process tree owned by this compilation."""
    if process.poll() is not None:
        return
    if os.name == 'nt':
        taskkill = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'taskkill.exe'
        subprocess.run([str(taskkill), '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=15, check=False, creationflags=subprocess.CREATE_NO_WINDOW,
                       env=safe_child_env(taskkill, Path(os.environ.get('TEMP', '.')).resolve()))
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def _preflight(source_dir: Path, main: Path) -> list[dict]:
    issues = []
    if not _within(main, source_dir) or not main.is_file() or main.suffix.lower() != '.tex':
        return [_issue('UNSAFE_MAIN_PATH', '入口必须是受控源码目录中的现有 TeX 文件。')]
    total = 0
    for path in source_dir.rglob('*'):
        rel = path.relative_to(source_dir).as_posix()
        if path.is_symlink() or not _within(path.resolve(), source_dir):
            issues.append(_issue('UNSAFE_DEPENDENCY', '拒绝符号链接或越界依赖。', file=rel))
            continue
        if not path.is_file():
            continue
        if any(p.startswith('.') for p in path.relative_to(source_dir).parts):
            issues.append(_issue('HIDDEN_ATTACHMENT', '源码快照不能包含隐藏文件或配置。', file=rel))
            continue
        total += path.stat().st_size
        if path.suffix.lower() not in ALLOWED_ASSETS:
            issues.append(_issue('DANGEROUS_ATTACHMENT', '不接受此类编译附件。', file=rel))
            continue
        if path.suffix.lower() not in {'.tex', '.sty', '.cls', '.pgf', '.tikz', '.md', '.txt', '.json'}:
            continue
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            try:
                text = path.read_text(encoding='gb18030')
            except UnicodeError:
                issues.append(_issue('UNKNOWN_ENCODING', '无法无损读取 TeX 编码。', file=rel))
                continue
        active = re.sub(r'(?<!\\)%[^\n]*', '', text)
        # This preflight intentionally does not claim to emulate TeX expansion.
        if '^^' in active:
            issues.append(_issue('TEX_CHARACTER_REENCODING', '不接受可能隐藏命令的 TeX 字符重编码。', file=rel))
        for match in re.finditer(r'\\(?:openin|openout|read|write|write18|catcode|scantokens|directlua|luaexec|special|csname|@@input)(?![A-Za-z@])', active):
            issues.append(_issue('UNSAFE_TEX_COMMAND', '禁止直接读写文件、改变词法或执行外部代码的 TeX 命令。', file=rel,
                                 source_line=active.count('\n', 0, match.start()) + 1, command=match.group()))
        for match in re.finditer(r'\\(?:input|include|includegraphics)(?:\[[^]]*\])?\s*\{([^}]+)\}', active):
            dependency = match.group(1).replace('\\', '/')
            if dependency.startswith(('/', '|')) or PureWindowsPath(dependency).is_absolute() or '..' in Path(dependency).parts:
                issues.append(_issue('UNSAFE_DEPENDENCY', '依赖必须使用源码目录内相对路径。', file=rel,
                                     source_line=active.count('\n', 0, match.start()) + 1))
        contains_runtime_secret = any(value and len(value) >= 8 and value in text
            for key, value in os.environ.items()
            if any(marker in key.upper() for marker in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD')))
        if re.search(r'\bsk-[A-Za-z0-9_-]{8,}', text) or contains_runtime_secret:
            issues.append(_issue('SENSITIVE_SOURCE', '源码中发现疑似密钥，已阻止进入编译和导出。', file=rel))
    if total > MAX_OUTPUT_BYTES:
        issues.append(_issue('SOURCE_SIZE_LIMIT', '源码资源超过 200 MiB 限制。'))
    return issues


def parse_log(text: str) -> list[dict]:
    issues = []
    patterns = [
        ('UNDEFINED_CONTROL_SEQUENCE', r'Undefined control sequence', 'blocking'),
        ('MISSING_FILE', r'(?:File .+ not found|I can.t find file)', 'blocking'),
        ('TEX_FATAL', r'(?:Emergency stop|Fatal error|File ended while scanning|Runaway argument)', 'blocking'),
        ('INCOMPLETE_CONDITIONAL', r'Incomplete \\if[^\n]*', 'blocking'),
        ('LATEX_ERROR', r'(?:LaTeX Error|Package [^\n]+? Error):[^\n]*', 'blocking'),
        ('UNRESOLVED_REFERENCE', r'(?:There were undefined references|Reference .+ undefined|Citation .+ undefined)', 'blocking'),
        ('OVERFULL_BOX', r'Overfull \\[hv]box[^\n]*', 'blocking'),
        ('MISSING_GLYPH', r'Missing character[^\n]*', 'blocking'),
        ('FONT_SUBSTITUTION', r'(?:Font shape .+ undefined|Some font shapes were not available)', 'review'),
        ('UNDERFULL_BOX', r'Underfull \\[hv]box[^\n]*', 'info'),
    ]
    for rule, pattern, severity in patterns:
        for match in re.finditer(pattern, text):
            start = text.rfind('\n', 0, match.start()) + 1
            end = text.find('\n', match.end())
            line = text[start:end if end >= 0 else len(text)].strip()
            location = {'log_line': text.count('\n', 0, match.start()) + 1}
            source = re.search(r'([^\s:]+\.(?:tex|vrb|sty|cls)):(\d+):', line)
            if source:
                location.update(file=source.group(1), source_line=int(source.group(2)))
            issues.append(_issue(rule, scrub(line)[:800], severity=severity, **location))
    return issues


class TexCompiler:
    def __init__(self, xelatex_path: str | None = None, timeout: float = 120):
        self.xelatex_path = xelatex_path
        self.timeout = min(max(float(timeout), .1), 480)

    def compile(self, source_dir: Path, main_file: str, output_dir: Path, *, trusted: bool,
                cancel_check: Callable[[], bool] | None = None) -> dict:
        source_dir, output_dir = Path(source_dir).resolve(), Path(output_dir).resolve()
        result = {'status': 'BLOCKED', 'pdf_path': None, 'issues': [], 'log_paths': [],
                  'engine': None, 'passes': 0, 'compile_mode': 'trusted_local',
                  'isolation': 'NOT_IMPLEMENTED', 'limitations': ['原生可信本机编译不是文件系统或网络隔离沙箱。']}
        if not trusted:
            result['issues'] = [_issue('TRUST_CONFIRMATION_REQUIRED', '请确认本次输入和模板来自可信来源。')]
            return result
        if source_dir == output_dir or _within(output_dir, source_dir):
            result['issues'] = [_issue('BUILD_LOCATION', '构建目录必须与源文件目录分离。')]
            return result
        if output_dir.exists() and any(output_dir.iterdir()):
            result['issues'] = [_issue('STALE_BUILD_DIRECTORY', '构建目录非空；请使用新的版本目录，禁止复用旧 PDF。')]
            return result
        main = (source_dir / main_file).resolve()
        result['issues'] = _preflight(source_dir, main)
        if result['issues']:
            return result
        engine = resolve_xelatex(self.xelatex_path, forbidden_roots=[source_dir, output_dir])
        if engine is None:
            result['issues'] = [_issue('XELATEX_NOT_FOUND', '未找到已安装 XeLaTeX 的可信绝对路径。')]
            return result
        output_dir.mkdir(parents=True, exist_ok=True)
        env = safe_child_env(engine, output_dir)
        for key in ('TEMP', 'TEXMFHOME', 'TEXMFCONFIG', 'TEXMFVAR'):
            Path(env[key]).mkdir(parents=True, exist_ok=True)
        try:
            version = subprocess.run([str(engine), '--version'], cwd=output_dir, env=env,
                capture_output=True, timeout=15, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            version_text = version.stdout.decode('utf-8', 'replace')
            if version.returncode or 'XeTeX' not in version_text:
                raise ValueError('Executable did not identify as XeTeX')
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            result['issues'] = [_issue('ENGINE_VERIFICATION', scrub(str(exc)))]
            return result
        result['engine'] = {'path': str(engine), 'version': version_text.splitlines()[0]}
        for path in source_dir.rglob('*'):
            if path.is_file() and path.suffix.lower() not in {'.md', '.txt'}:
                destination = output_dir / path.relative_to(source_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        (output_dir / '.math-agent-engine.json').write_text(json.dumps(result['engine']), encoding='utf-8')
        main_relative = main.relative_to(source_dir)
        # Job name is fixed, ASCII and does not depend on an uploaded filename.
        stem = {'lecture.tex': 'lecture', 'slides.tex': 'slides'}.get(main.name, 'document')
        command = [str(engine), '-interaction=nonstopmode', '-halt-on-error', '-file-line-error',
                   '-no-shell-escape', '-recorder', '-synctex=1', f'-jobname={stem}',
                   '-output-directory=.', str(main_relative)]
        result['command'] = command
        previous = None
        stable = False
        started = time.monotonic()
        final_text = ''
        cancelled = False
        for pass_number in range(1, 5):
            if cancel_check and cancel_check():
                result['status'] = 'CANCELLED'
                cancelled = True
                break
            result['passes'] = pass_number
            stdout_path = output_dir / f'pass-{pass_number}.stdout.log'
            process = None
            stop_rule = None
            with stdout_path.open('wb') as stream:
                try:
                    process = subprocess.Popen(command, cwd=output_dir, env=env, stdin=subprocess.DEVNULL,
                        stdout=stream, stderr=subprocess.STDOUT, shell=False,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                        start_new_session=os.name != 'nt')
                    pass_started = time.monotonic()
                    while process.poll() is None:
                        if cancel_check and cancel_check():
                            stop_rule = 'CANCELLED'
                        elif time.monotonic() - pass_started > self.timeout or time.monotonic() - started > min(480, self.timeout * 4):
                            stop_rule = 'COMPILE_TIMEOUT'
                        elif stdout_path.stat().st_size > MAX_LOG_BYTES:
                            stop_rule = 'LOG_SIZE_LIMIT'
                        elif bounded_directory_size(output_dir) > MAX_OUTPUT_BYTES:
                            stop_rule = 'OUTPUT_SIZE_LIMIT'
                        if stop_rule:
                            terminate_tree(process)
                            break
                        time.sleep(.1)
                except (OSError, subprocess.SubprocessError) as exc:
                    if process and process.poll() is None:
                        terminate_tree(process)
                    result['issues'].append(_issue('COMPILER_PROCESS_ERROR', scrub(str(exc))))
                    error_path = output_dir / f'pass-{pass_number}.process-error.json'
                    error_path.write_text(json.dumps({'type':type(exc).__name__,'message':scrub(str(exc))},ensure_ascii=False),encoding='utf-8')
                    result['log_paths'].append(str(error_path))
                    result['status'] = 'FAIL'
            final_text = scrub(stdout_path.read_bytes()[:MAX_LOG_BYTES].decode('utf-8', 'replace'))
            stdout_path.write_text(final_text, encoding='utf-8')
            result['log_paths'].append(str(stdout_path))
            texlog = output_dir / f'{stem}.log'
            if texlog.exists():
                cleaned = scrub(texlog.read_bytes()[:MAX_LOG_BYTES].decode('utf-8', 'replace'))
                texlog.write_text(cleaned, encoding='utf-8')
                copied_log = output_dir / f'pass-{pass_number}.tex.log'
                copied_log.write_text(cleaned, encoding='utf-8')
                result['log_paths'].append(str(copied_log))
                final_text = cleaned
            if stop_rule:
                result['status'] = 'CANCELLED' if stop_rule == 'CANCELLED' else 'FAIL'
                result['issues'].append(_issue(stop_rule, '编译进程树已停止；保留本轮日志和源码。'))
                cancelled = stop_rule == 'CANCELLED'
                break
            if process is None or process.returncode != 0 or result['status'] == 'FAIL':
                result['status'] = 'FAIL'
                result['issues'].extend(parse_log(final_text))
                terminal_rules = {'UNDEFINED_CONTROL_SEQUENCE', 'MISSING_FILE', 'TEX_FATAL', 'INCOMPLETE_CONDITIONAL', 'LATEX_ERROR'}
                if not any(i['rule_id'] in terminal_rules for i in result['issues']):
                    result['issues'].append(_issue('COMPILE_FAILED',
                        'XeLaTeX 非零退出；日志末尾：' + '\n'.join(final_text.splitlines()[-12:])[-1500:]))
                break
            auxiliary = {suffix: hashlib.sha256((output_dir / (stem + suffix)).read_bytes()).hexdigest()
                         for suffix in AUX_SUFFIXES if (output_dir / (stem + suffix)).exists()}
            rerun = bool(re.search(r'(?:Rerun to get|Rerun LaTeX|Please rerun LaTeX|Label\(s\) may have changed)', final_text))
            if pass_number >= 2 and auxiliary == previous and not rerun:
                stable = True
                result['status'] = 'PASS'
                break
            previous = auxiliary
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        if cancelled or result['status'] in ('FAIL', 'CANCELLED'):
            return result
        result['issues'].extend(parse_log(final_text))
        if not stable:
            result['issues'].append(_issue('UNSTABLE_REFERENCES', '四轮后辅助文件或交叉引用仍不稳定。'))
            result['status'] = 'FAIL'
            return result
        pdf = output_dir / f'{stem}.pdf'
        if not pdf.is_file() or not pdf.read_bytes().startswith(b'%PDF-'):
            result['issues'].append(_issue('MISSING_FRESH_PDF', '本次构建没有生成可读 PDF。'))
            result['status'] = 'FAIL'
            return result
        try:
            from .pdfcheck import probe_pdf
            result['page_count'] = probe_pdf(pdf)['page_count']
            if not 1 <= result['page_count'] <= 5000:
                raise ValueError('PDF page count outside allowed range 1..5000')
        except Exception as exc:
            result['issues'].append(_issue('PDF_OPEN_FAILED', scrub(str(exc))))
            result['status'] = 'FAIL'
            return result
        fatal = {'UNDEFINED_CONTROL_SEQUENCE', 'MISSING_FILE', 'TEX_FATAL', 'UNRESOLVED_REFERENCE', 'INCOMPLETE_CONDITIONAL', 'LATEX_ERROR'}
        if any(i['rule_id'] in fatal for i in result['issues']):
            result['status'] = 'FAIL'
            return result
        if cancel_check and cancel_check():
            result['status'] = 'CANCELLED'
            return result
        result['pdf_path'] = str(pdf)
        result['pdf_sha256'] = hashlib.sha256(pdf.read_bytes()).hexdigest()
        result['auxiliary_hashes'] = previous or {}
        result['status'] = 'FAIL' if any(i['severity'] == 'blocking' for i in result['issues']) else 'PASS'
        return result
