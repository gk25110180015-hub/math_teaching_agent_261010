"""Shared, actionable build diagnostics for lecture and Beamer workflows."""
from .util import canonical


def unique_issues(issues):
    seen = set()
    result = []
    for issue in issues:
        key = canonical(issue)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def describe_issue(issue):
    location = issue.get('location') or {}
    where = [str(issue[k]) for k in ('unit_id', 'frame_id') if issue.get(k)]
    if location.get('file'):
        where.append(str(location['file']))
    if location.get('source_line'):
        where.append('第 '+str(location['source_line'])+' 行')
    label = ' · '.join([issue.get('rule_id', 'QUALITY'), *where])
    return label + '：' + issue.get('message', '未通过检查') + (
        '\n处理方法：'+issue['suggested_action'] if issue.get('suggested_action') else '')


def blocking_message(quality):
    issues = [i for i in unique_issues(quality.get('issues', [])) if i.get('severity') == 'blocking']
    details = '\n'.join(describe_issue(i)[:550] for i in issues[:5])
    if not details:
        details = '；'.join(k+'='+str(quality.get(k, {}).get('status', 'NOT_RUN'))
                           for k in ('compile', 'fidelity', 'layout'))
    more = f'\n另有 {len(issues)-5} 项，见质量报告。' if len(issues)>5 else ''
    return ('本次构建未通过检查：\n'+details+more+
            '\n已保留草稿、日志和原审批。请查看 quality_report.json 中的具体位置及处理方法；条件未改变时直接重试会再次遇到同一问题。')
