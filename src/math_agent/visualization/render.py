"""Trusted renderer process. Generated code stays in browser Web Workers."""
import base64
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from ..util import AgentError, write_json, scrub
from .contracts import scene_requirements


def browser_path():
    paths = [os.environ.get('MATH_AGENT_BROWSER_PATH'),
             r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
             r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
             r'C:\Program Files\Google\Chrome\Application\chrome.exe']
    return next((p for p in paths if p and Path(p).is_file()), None)


def child_environment():
    allowed = {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LOCALAPPDATA', 'APPDATA', 'USERPROFILE',
               'PATH', 'PATHEXT', 'COMSPEC', 'HOME', 'LANG', 'MATH_AGENT_BROWSER_PATH', 'PLAYWRIGHT_BROWSERS_PATH'}
    return {k: v for k, v in os.environ.items() if k.upper() in allowed}


def render_video(directory, duration, active=lambda: True, *, probe_only=False):
    directory = Path(directory).resolve()
    with (directory / 'render.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'math_agent.visualization.render', str(directory)] + (['--probe-only'] if probe_only else []),
            env=child_environment(), stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + duration + 100
        try:
            while process.poll() is None:
                if not active():
                    raise AgentError('CANCELLED', '任务已取消，停止渲染')
                if time.monotonic() > deadline:
                    raise AgentError('VISUAL_RENDER_TIMEOUT', '视频渲染超时；代码与日志已保留')
                time.sleep(.2)
        finally:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run([str(Path(os.environ['SYSTEMROOT']) / 'System32/taskkill.exe'),
                                    '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    process.terminate()
                process.wait(timeout=10)
    report_path = directory / 'render_report.json'
    if not report_path.is_file():
        raise AgentError('VISUAL_RENDER_FAILED', '浏览器未完成渲染；请检查 render.log 和 Playwright / Edge 安装')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if not probe_only and (process.returncode or report['status'] != 'PASS'):
        raise AgentError(report.get('code', 'VISUAL_RENDER_FAILED'), report.get('error', '视频渲染失败'))
    return report


def probe_program(directory, active=lambda: True):
    return render_video(directory, 0, active, probe_only=True)


def review_evidence(report):
    """Bound model context; full numerical probes remain in the diagnostic artifact."""
    def compact(sample):
        return {k: sample[k] for k in ('time', 'scene_id', 'mode', 'controls', 'disabled', 'metrics', 'title', 'caption', 'error') if k in sample}
    def drawing(sample):
        evidence = sample.get('drawing_evidence', {})
        result = {}
        for kind, items in evidence.items():
            result[kind] = []
            for item in items:
                if not isinstance(item, dict):
                    result[kind].append(item)
                    continue
                entry = {key: value for key, value in item.items()
                         if not (key == 'transform' and value == [1,0,0,1,0,0])
                         and not (key in ('x','y') and 'bounds' in item)}
                for key in ('bounds', 'box', 'transform'):
                    if key in entry:
                        entry[key] = [round(v, 1) if isinstance(v, (float, int)) else v for v in entry[key]]
                if kind != 'paints' or entry not in result[kind]:
                    result[kind].append(entry)
        return result
    scenes = []
    for sample in report.get('scenes', []):
        siblings = [s for s in report['scenes'] if s.get('scene_id') == sample.get('scene_id')]
        # Numerical/time evidence is kept for every frame. Geometry at 30% and 70%
        # covers both staged examples without repeating all Canvas text five times.
        detailed = len(siblings) <= 2 or any(sample is siblings[i] for i in (1, len(siblings)-2))
        scenes.append({**compact(sample), 'plot_text': sample.get('plot_text', []),
            **({'drawing_evidence': drawing(sample)} if detailed else {})})
    return {'status': report['status'], 'issues': report.get('issues', []), 'error': report.get('error'),
            'scenes': scenes,
            'controls': [{'id': c['id'], 'status': c['status'],
                'probes': [{'time': p['time'], 'values': [compact(v) for v in p['values']]}
                           for p in c['probes']]}
                         for c in report.get('controls', [])]}


def metric_issues(value, path='metrics'):
    if isinstance(value, (dict, list)):
        if not value:
            return [path + ' 不能为空']
        items = value.items() if isinstance(value, dict) else enumerate(value)
        return [issue for key, item in items for issue in metric_issues(item, f'{path}.{key}')]
    if isinstance(value, bool) or (isinstance(value, str) and value.strip()):
        return []
    if isinstance(value, (float, int)) and math.isfinite(value):
        return []
    return [path + ' 必须为有限数值、布尔状态或非空文字；不能为 null、NaN 或 Infinity']


def finite_metrics(value):
    return not metric_issues(value)


def control_probe_values(control):
    """Include an interior value: the ends of a rotation slider can be equivalent."""
    middle = control['min'] + round((control['max'] - control['min']) / (2 * control['step'])) * control['step']
    return list(dict.fromkeys([control['min'], max(control['min'], min(control['max'], middle)), control['max']]))


def scene_probe_times(story):
    """A display control may be intentionally used in only one of the scenes."""
    total = sum(s['seconds'] for s in story['scenes'])
    elapsed = 0; times = [.37, .73]
    for scene in story['scenes']:
        times.append((elapsed + scene['seconds'] / 2) / total)
        elapsed += scene['seconds']
    return sorted(set(times))


def presentation_probe_times(story):
    return sorted({t for scene in scene_requirements(story) for t in scene['sample_times']})


def text_overflow_issues(sample):
    issues = []
    for item in sample.get('drawing_evidence', {}).get('texts', []):
        if item.get('clipped') or len(item.get('bounds', [])) != 4:
            continue  # A clipped axis label cannot establish visible overflow.
        left, top, right, bottom = item['bounds']
        if bottom > 68 and top < 435 and (left < -1 or right > 961):
            issues.append(f"绘图文字超出画布：{item['text']!r}，横向范围 [{left:.1f}, {right:.1f}]；请按可用宽度换行或缩短文字")
    return issues[:8]


def run_renderer(directory, probe_only=False):
    from playwright.sync_api import sync_playwright
    project = json.loads((directory / 'project.json').read_text(encoding='utf-8'))
    program = project['program']
    report = {'status': 'PASS', 'samples': [], 'scenes': [], 'controls': [], 'issues': [], 'network_requests_blocked': 0,
              'human_visual_review': 'NOT_RUN', 'code_execution': 'browser_web_worker'}
    with sync_playwright() as manager:
        browser = manager.chromium.launch(headless=True, executable_path=browser_path())
        try:
            context = browser.new_context(viewport={'width': 1040, 'height': 850}, service_workers='block', accept_downloads=False)
            document = (directory / 'interactive.html').read_text(encoding='utf-8')
            url = 'https://visualization.invalid/lesson'
            def route(request):
                if request.request.url == url and request.request.is_navigation_request():
                    request.fulfill(status=200, content_type='text/html', body=document)
                else:
                    report['network_requests_blocked'] += 1
                    request.abort()
            context.route('**/*', route)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(url)
            page.evaluate('() => window.visualization.ready')
            invalid_methods = set()
            def sample(t, params=None, mode='presentation'):
                result = page.evaluate('async ([t,p,mode]) => await window.visualization.render(t,p,{mode})', [t, params or {}, mode])
                issues = metric_issues(result.get('metrics'))
                if issues:
                    raise ValueError('动画数学状态无效：' + '; '.join(issues[:8]))
                report['issues'].extend(text_overflow_issues(result))
                for call in result.get('drawing_evidence', {}).get('invalid_calls', []):
                    if call['method'] not in invalid_methods:
                        invalid_methods.add(call['method'])
                        report['issues'].append('无效 Canvas 绘图调用：' + call['method'] + '(' + ', '.join(call['arguments']) + ')；' + call['reason'] + '；请检查所有同类调用点')
                return result
            signatures = []
            for t in (0.0, .25, .5, .75, 1.0):
                result = sample(t)
                signatures.append(result['plot_signature'])
                report['samples'].append({'time': t, **result})
                if t in (.0, .5, 1.0):
                    page.locator('#scene').screenshot(path=str(directory / f'frame-{int(t*100):03d}.png'))
            if len(set(signatures)) < 3:
                report['issues'].append('绘图区没有随时间发生充分变化，不能把静态画面交付为动画')
            times = scene_probe_times(project['story'])
            baselines = {t: sample(t) for t in times}
            # A midpoint alone misses alternating examples or a hold at either extremum.
            report['scenes'] = []
            for t in presentation_probe_times(project['story']):
                result = baselines[t] if t in baselines else sample(t)
                report['scenes'].append({'time': t, **result})
            for control in program['controls']:
                probes = []
                for t in times:
                    values = []
                    for value in control_probe_values(control):
                        try:
                            state = sample(t, {**baselines[t]['controls'], control['id']: value}, 'explore')
                            values.append({'value': value, **state})
                        except Exception as error:
                            values.append({'value': value, 'error': scrub(str(error))[:600]})
                    enabled = [v for v in values if control['id'] not in v.get('disabled', {})]
                    issue = next((v['error'] for v in values if v.get('error')), None)
                    # Version 2 must either implement an enabled control in this scene or explain its disabling.
                    if not issue and program.get('runtime_version') == 2 and len(enabled)>1 and len({v['plot_signature'] for v in enabled})==1:
                        issue = f"镜头 {baselines[t]['scene_id']} 启用的控件 {control['id']} 未实际改变画面"
                    probes.append({'time': t, 'values': values, 'issue': issue})
                issues = [p['issue'] for p in probes if p['issue']]
                if not any(len({v.get('plot_signature') for v in p['values'] if not v.get('error') and control['id'] not in v.get('disabled', {})})>1 for p in probes):
                    issues.append('交互参数在所有适用镜头都未实际改变画面：' + control['id'])
                report['issues'].extend(issues)
                report['controls'].append({'id': control['id'], 'status': 'FAIL' if issues else 'PASS', 'probes': probes})
            report['issues'] = list(dict.fromkeys(report['issues']))
            if errors:
                report['issues'].extend(errors)
            if report['issues']:
                report.update(status='FAIL', error='; '.join(report['issues'])[:2500], code='VISUAL_CONTROL_FAILED')
                return report
            if probe_only:
                return report
            result = page.evaluate('() => window.visualization.record()')
            data = base64.b64decode(result.pop('data'), validate=True)
            if not data.startswith(b'\x1aE\xdf\xa3') or len(data) < 1024 or result['frames'] < 10 or result['width'] != 960 or result['height'] != 540:
                raise ValueError('视频字节、帧数或解码尺寸校验失败')
            (directory / 'video.webm').write_bytes(data)
            report['video'] = {**result, 'bytes': len(data)}
            if errors:
                raise ValueError('; '.join(errors)[:2000])
            return report
        except Exception as error:
            report.update(status='FAIL', error=scrub(str(error))[:2500], code='VISUAL_RENDER_FAILED')
            return report
        finally:
            browser.close()


if __name__ == '__main__':
    target = Path(sys.argv[1]).resolve()
    try:
        output = run_renderer(target, probe_only='--probe-only' in sys.argv)
    except Exception as error:
        output = {'status': 'FAIL', 'error': scrub(str(error))[:2500], 'code': 'VISUAL_RENDER_FAILED'}
    write_json(target / 'render_report.json', output)
    sys.exit(0 if output['status'] == 'PASS' else 1)
