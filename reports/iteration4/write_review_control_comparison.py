"""Read completed frozen v5/v6 evidence only; no model, task, or source changes."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
RUNS = {'v5': OUT/'live-review-controls-v5-20260920-1515',
        'v6': OUT/'live-review-controls-v6-20260920-1530'}
MODELS = ['gpt6', 'deepseek-flash', 'deepseek-v4-pro']
CASES = ['R01', 'R02']
EXPECTED_MODELS = {'gpt6': 'gpt-6-astra', 'deepseek-flash': 'deepseek-flash', 'deepseek-v4-pro': 'deepseek-v4-pro'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def evidence(path):
    data = path.read_bytes()
    return {'path': path.relative_to(ROOT).as_posix(), 'raw_sha256': sha(data), 'bytes': len(data)}


def link(path, title):
    return f'[{title}]({Path(os.path.relpath(path,OUT)).as_posix()})'


states = {}
frozen_bytes = {}
for version, folder in RUNS.items():
    raw = (folder/'state.json').read_bytes()
    state = json.loads(raw)
    if state['status'] == 'RUNNING' or len(state['results']) != 6:
        raise SystemExit(f'NOT_RUN: {version} is not final; status={state["status"]}, results={len(state["results"])}. No report written.')
    assert state['model_order'] == MODELS and state['automatic_fallback'] is False
    states[version] = state
    frozen_bytes[version] = raw

fixtures = {version: json.loads((folder/'fixtures-local-only.json').read_bytes()) for version, folder in RUNS.items()}
assert fixtures['v5'] == fixtures['v6']
assert states['v5']['fixture_sha256'] == states['v6']['fixture_sha256']
assert [case['id'] for case in fixtures['v5']] == CASES
case_map = {case['id']: case for case in fixtures['v5']}
baseline = ROOT/'reports/iteration2/review-context-calibration-fixtures.json'
assert sha(baseline.read_bytes()) == states['v5']['fixture_sha256']
cases_identity = {name: {'kind': case['expectation']['kind'], 'input_sha256': sha(canonical(case['input']).encode('utf-8')),
                        'expectation_sha256': sha(canonical(case['expectation']).encode('utf-8')),
                        'expected_flagged_unit_ids': case['expectation']['expected_flagged_unit_ids'],
                        'expected_blocking_unit_ids': case['expectation']['expected_blocking_unit_ids']}
                  for name, case in case_map.items()}

versions = {}
matrix = {}
for version, folder in RUNS.items():
    state = states[version]
    prompt_path = folder/'prompts/reviewer_math.md'
    assert sha(prompt_path.read_bytes()) == state['prompt_sha256']
    request_events = [record for record in state['requests'] if record['type'] == 'request']
    assert len(request_events) == state['request_count']
    failures = [record for record in state['requests'] if (isinstance(record.get('http_status'), int) and record['http_status'] >= 400)
                or record.get('code') or record.get('validation_errors') or record.get('error_code')]
    result_rows = []
    seen = set()
    for row in state['results']:
        model, case_id = row['model_id'], row['case_id']
        assert (model, case_id) not in seen
        seen.add((model, case_id))
        actual = row.get('actual_response', {})
        review_path = folder/model/(case_id+'-review.json')
        review = json.loads(review_path.read_bytes()) if review_path.exists() else None
        output = {'model_id': model, 'case_id': case_id, 'case_kind': case_map[case_id]['expectation']['kind'],
                  'started_at_utc': row['started_at'], 'finished_at_utc': row['finished_at'],
                  'case_wall_seconds': round((datetime.fromisoformat(row['finished_at'])-datetime.fromisoformat(row['started_at'])).total_seconds(), 3),
                  'response_status': row['status'], 'recorded_local_classification': row['classification_status'],
                  'request_count': sum(event['model_id'] == model and event['case_id'] == case_id for event in request_events),
                  'preferred_model_id': actual.get('preferred_model_id'), 'actual_model_id': actual.get('model_id'),
                  'requested_api_model': actual.get('requested_model'), 'reported_model': actual.get('reported_model'),
                  'expected_api_model': EXPECTED_MODELS[model], 'http_status': actual.get('http_status'),
                  'transport_status': actual.get('transport_status'), 'call_id': actual.get('call_id'),
                  'endpoint': actual.get('base_url'), 'usage': actual.get('usage'),
                  'streaming': actual.get('streaming'), 'temperature': actual.get('temperature'),
                  'thinking': actual.get('thinking'), 'reasoning_effort': actual.get('reasoning_effort'),
                  'request_messages_hash': actual.get('input_hash'), 'provider_prompt_text_hash': actual.get('prompt_hash'),
                  'review_schema_hash': actual.get('schema_hash'), 'error': row.get('error')}
        if review is not None:
            ids = set(case_map[case_id]['input']['actual_unit_ids'])
            checked = review['checked_unit_ids']
            flagged = {item['unit_id'] for item in review['issues'] if item['severity'] in ('blocking', 'review')}
            blocking = {item['unit_id'] for item in review['issues'] if item['severity'] == 'blocking'}
            coverage = set(checked) == ids and len(checked) == len(ids)
            valid_ids = all(issue['unit_id'] in ids for issue in review['issues'])
            expected = case_map[case_id]['expectation']
            matched = not flagged if expected['kind'] == 'CORRECT_CONTROL' else (
                set(expected['expected_flagged_unit_ids']).issubset(flagged)
                and set(expected['expected_blocking_unit_ids']).issubset(blocking))
            classification = 'PASS' if coverage and valid_ids and matched else 'FAIL'
            assert classification == row['classification_status']
            if expected['kind'] == 'CORRECT_CONTROL':
                finding = 'POSITIVE_FALSE_ALARM' if flagged else 'CORRECT_CONTROL_ACCEPTED'
            elif set(expected['expected_flagged_unit_ids']).issubset(flagged):
                finding = 'ERROR_DETECTED_AND_BLOCKING' if blocking else 'ERROR_DETECTED_SEVERITY_MISMATCH'
            else:
                finding = 'EXPECTED_ERROR_NOT_FLAGGED'
            output.update(recomputed_local_classification=classification, coverage_complete=coverage, issue_ids_valid=valid_ids,
                flagged_unit_ids=sorted(flagged), blocking_unit_ids=sorted(blocking), severity_counts=dict(Counter(issue['severity'] for issue in review['issues'])),
                workflow_would_require_repair=bool(flagged), finding_category=finding,
                response_evidence=evidence(review_path), issues=review['issues'], limitations=review['limitations'])
        else:
            output.update(recomputed_local_classification='NOT_RUN', finding_category='NO_VALIDATED_RESPONSE', workflow_would_require_repair=None)
        output['selected_and_returned_models_match'] = (actual.get('preferred_model_id') == model == actual.get('model_id')
            and actual.get('requested_model') == actual.get('reported_model') == EXPECTED_MODELS[model])
        result_rows.append(output)
        matrix[(version, model, case_id)] = output
    assert seen == {(model, case_id) for model in MODELS for case_id in CASES}
    versions[version] = {'recorded_run_status': state['status'], 'request_count': state['request_count'],
        'started_at_utc': state['created_at'], 'finished_at_utc': state['finished_at'],
        'run_wall_seconds': round((datetime.fromisoformat(state['finished_at'])-datetime.fromisoformat(state['created_at'])).total_seconds(), 3),
        'strict_matches': sum(row['recorded_local_classification'] == 'PASS' for row in result_rows),
        'validated_responses': sum(row['response_status'] == 'RESPONSE_VALIDATED' for row in result_rows),
        'positive_false_alarms': sum(row['finding_category'] == 'POSITIVE_FALSE_ALARM' for row in result_rows),
        'negative_detected': sum(row['case_id'] == 'R02' and row['workflow_would_require_repair'] is True for row in result_rows),
        'severity_only_mismatches': sum(row['finding_category'] == 'ERROR_DETECTED_SEVERITY_MISMATCH' for row in result_rows),
        'all_model_labels_match_selection': all(row['selected_and_returned_models_match'] for row in result_rows),
        'http_error_statuses': sorted({event['http_status'] for event in failures if isinstance(event.get('http_status'), int) and event['http_status'] >= 400}),
        'failure_or_schema_error_events': failures, 'automatic_fallback': False,
        'prompt_evidence': evidence(prompt_path), 'state_evidence': evidence(folder/'state.json'),
        'two_cases_snapshot_evidence': evidence(folder/'fixtures-local-only.json'),
        'results': result_rows}

limitations = [
    '仅两个已知控制题、每模型每版本各一次；V6在读取V5相同题的反馈后修改。这是针对性回归，不是盲测、留出集或总体数学准确率估计。',
    '没有模型权重训练。修改的是通用审阅提示词；两版本fixture与本地预期相同，预期没有发送给模型。',
    '严格本地评分对负例要求blocking；真实工作流将review与blocking都作为未解决问题处理。严重度不符不能描述为模型漏检。',
    '单题墙钟耗时包含网络、生成、结构验证及结果落盘，未隔离服务负载或采样波动，不能据两点推断性能提升或提示词的因果效应。',
    'reported_model是服务端返回标签，不是对供应商后台模型身份的独立鉴定。此次成功记录不保证未来API可用。',
    '两题没有覆盖一般几何级数、部分和初值、完整章目标与PDF排版；不能据此宣称真实章节制作效果或人工数学/视觉验收通过。',
    '未解析或传播模型隐藏推理；审读对象是归档的最终结构化回复。',
]
result = {'schema_version': 1, 'status': 'COMPARISON_COMPLETE', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'evidence_kind': 'REAL_API_TARGETED_REGRESSION', 'versions': versions,
    'baseline_fixture_evidence': evidence(baseline), 'cases': cases_identity,
    'model_order': MODELS, 'same_case_inputs_verified': True, 'same_expectations_verified': True,
    'expectations_sent_to_models': False, 'weight_training': False, 'blind_test': False,
    'teacher_mathematical_review': 'NOT_RUN', 'human_visual_acceptance': 'NOT_RUN',
    'windows_compile': 'NOT_APPLICABLE_TO_THESE_TEXT_CONTROLS', 'new_api_calls_by_report': 0,
    'existing_task_state_modified': False, 'limitations': limitations}

finding_labels = {'POSITIVE_FALSE_ALARM': '正确对照被误报', 'CORRECT_CONTROL_ACCEPTED': '正确对照未被阻断',
    'ERROR_DETECTED_AND_BLOCKING': '识错且 blocking', 'ERROR_DETECTED_SEVERITY_MISMATCH': '识错但仅 review',
    'EXPECTED_ERROR_NOT_FLAGGED': '预期错误未标记', 'NO_VALIDATED_RESPONSE': '无有效响应'}

def summary(row):
    severities=' / '.join(f'{name}×{count}' for name,count in row.get('severity_counts', {}).items()) or '无问题'
    return f'{row["recorded_local_classification"]}；{severities}'


lines = ['# 真实审阅同题对照：v5 → v6', '',
    f'两版本各对三个模型运行相同的一正一负控制题。严格本地预期符合数从 **{versions["v5"]["strict_matches"]}/6** 变为 **{versions["v6"]["strict_matches"]}/6**。这是一组针对性回归；应结合下面的逐题识错与严重度记录阅读，不能直接称为模型总体准确率。', '',
    '## 固定条件与判定', '',
    'R01 的完整连续定义先给一般等价关系，随后追加两函数均趋零的条件，既有预期为正确，不应出现 review/blocking。R02 明确取消趋零条件却仍称等价无穷小，既有预期为错误且要求 blocking。预期均在本地比较，没有发送给模型。warning 不影响这组严格分类。', '',
    '三个模型按 gpt6 → deepseek-flash → deepseek-v4-pro 顺序执行，每个模型先 R01 后 R02；本实验关闭自动降级以比较所选模型本身。gpt6 的请求及返回模型为 gpt-6-astra，启用 SSE、temperature=0.1；两个 DeepSeek 模型使用 thinking enabled、high、非流式。', '',
    '## 逐模型逐题结果', '',
    '| 模型 | 控制题 | v5 严格分类 / 严重度 | v6 严格分类 / 严重度 | 单题墙钟秒 v5 → v6 | 原始回复 |',
    '|---|---|---|---|---|---|']
for model in MODELS:
    for case_id in CASES:
        old, new = matrix[('v5', model, case_id)], matrix[('v6', model, case_id)]
        citations=' / '.join(link(RUNS[version]/model/(case_id+'-review.json'),version)
            if (RUNS[version]/model/(case_id+'-review.json')).exists() else link(RUNS[version]/'state.json',version+'无有效回复')
            for version in RUNS)
        lines.append(f'| {model} | {case_id} | {summary(old)} | {summary(new)} | {old["case_wall_seconds"]:.3f} → {new["case_wall_seconds"]:.3f} | {citations} |')
lines += ['',
    'v5 的 gpt6 和 Flash 在 R01 都把连续定义的承接视为核心歧义，给出 review；按冻结的完整上下文预期，这是两个正例误报。gpt6 举出的两个趋零但不等价函数不满足前句已保留的等价前提，不能据此证明该完整定义有数学错误。Flash 的依据是读者可能不把前句当作持续前提，也属于这组条件承接回归针对的过度阻断。', '',
    'v5 的三个模型都实际识别了 R02 错误。Pro 明确给出 p=q=1 的合法反例并指出“等价无穷小”不应取消趋零要求，但严重度仅为 review，所以未满足本地要求的 blocking。这是**识错但严重度不符，不是漏检**；真实工作流同样会保留疑点并要求处理。', '',
    'v6 逐题结果解读：', '']
for model in MODELS:
    first, second = matrix[('v6', model, 'R01')], matrix[('v6', model, 'R02')]
    lines.append(f'- {model}：R01 {finding_labels[first["finding_category"]]}；R02 {finding_labels[second["finding_category"]]}。')
lines += ['', '## API、实际模型与时延', '']
for version, data in versions.items():
    matched_models=sum(row['selected_and_returned_models_match'] for row in data['results'])
    lines.append(f'- {version}：{data["request_count"]} 次真实请求、{data["validated_responses"]}/6 结构有效回复；首选、实际调用及回传模型标签 {matched_models}/6 一致；HTTP 错误状态 {data["http_error_statuses"] or "未观察到"}；错误/结构修复记录 {len(data["failure_or_schema_error_events"])} 条；整轮墙钟 {data["run_wall_seconds"]:.3f} 秒。')
lines += ['',
    '逐条核对首选 model_id、实际调用 model_id、requested_model 与 reported_model；结果详见 JSON 中每条记录。没有把备用模型的成功算作首选模型成功。每个版本的状态文件包含完整请求时序、结构验证与 usage；本报告未新增请求。上述时延没有控制供应商负载，不据此给模型速度排名或宣称提示词造成加速。', '',
    '## 指纹与复现证据', '',
    '| 证据 | raw SHA256 |', '|---|---|',
    f'| {link(baseline,"原始控制题文件")} | `{sha(baseline.read_bytes())}` |']
for version, data in versions.items():
    for label, key, path in [('冻结提示词', 'prompt_evidence', RUNS[version]/'prompts/reviewer_math.md'),
                             ('最终状态', 'state_evidence', RUNS[version]/'state.json'),
                             ('两题及本地预期快照', 'two_cases_snapshot_evidence', RUNS[version]/'fixtures-local-only.json')]:
        lines.append(f'| {link(path,version+" "+label)} | `{data[key]["raw_sha256"]}` |')
lines += ['',
    '已验证两版冻结题目与预期完全相同。JSON 另给每题独立 input/expectation 指纹及每份最终回复 raw SHA。provider 的 input_hash 实际覆盖整个 messages（含 system 提示词），所以 v5/v6 的该值不同是预期现象，不能据此认定题目改变。', '',
    '## 解释边界', '', *[f'- {item}' for item in limitations], '',
    '人工数学与视觉验收均 NOT_RUN；这些文字控制题不包含 Windows 编译验收。']

for version, folder in RUNS.items():
    assert (folder/'state.json').read_bytes() == frozen_bytes[version], 'State changed while comparing; do not publish a mixed snapshot.'
targets = [OUT/'REVIEW_CONTROL_COMPARISON.json', OUT/'REVIEW_CONTROL_COMPARISON.md']
if any(path.exists() for path in targets):
    raise SystemExit('Refuse to overwrite an existing final comparison.')
targets[0].write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
targets[1].write_text('\n'.join(lines)+'\n', encoding='utf-8')
print(json.dumps({'status':'COMPARISON_COMPLETE','strict_matches':{key:value['strict_matches'] for key,value in versions.items()},
    'requests':{key:value['request_count'] for key,value in versions.items()},'new_api_calls':0},ensure_ascii=False))
