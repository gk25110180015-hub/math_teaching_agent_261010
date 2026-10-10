"""Opt-in fixed real API controls for explicit feedback disposition.

Independent from live chapter jobs. Expectations remain local. One completed
model judgment per case, with the ordinary provider's transient fallback only.
"""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

import math_agent.provider as provider_module
from math_agent.provider import CompatibleChatProvider
from math_agent.settings import PROJECT_ROOT, Settings
from math_agent.util import AgentError, digest, now, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--helper-file', required=True, type=Path)
    parser.add_argument('--prompt-file', required=True, type=Path)
    parser.add_argument('--fixtures-file', required=True, type=Path)
    args = parser.parse_args()
    if not args.execute_live:
        print('NOT_RUN: --execute-live and configured environment required.')
        return 0
    output = args.output_dir.resolve()
    if not output.is_relative_to((PROJECT_ROOT / 'reports').resolve()) or output.exists():
        parser.error('Choose a new output directory inside project reports.')
    settings = Settings().model_copy(update={'max_network_retries': 0, 'max_schema_repair_attempts': 0,
        'llm_connect_timeout_seconds': 30, 'llm_read_timeout_seconds': 600, 'llm_total_timeout_seconds': 600})
    if not settings.live_api_enabled:
        parser.error('Live API disabled in environment.')
    output.mkdir(parents=True, exist_ok=False)
    frozen = output / 'frozen'; frozen.mkdir()
    sources = {'helper.py': args.helper_file, 'reviewer_feedback.md': args.prompt_file,
               'fixtures-local-only.json': args.fixtures_file}
    fingerprints = {}
    for name, source in sources.items():
        data = source.read_bytes(); (frozen / name).write_bytes(data)
        fingerprints[name] = digest(data)
    spec = importlib.util.spec_from_file_location('math_agent._feedback_review_frozen', frozen / 'helper.py')
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    cases = json.loads((frozen / 'fixtures-local-only.json').read_bytes())['cases']
    original_prompts = provider_module.PROMPTS
    provider_module.PROMPTS = frozen
    state = {'created_at': now(), 'status': 'RUNNING', 'request_count': 0, 'request_limit': 12,
        'runner_sha256': digest(Path(__file__).read_bytes()),
        'preferred_model': 'gpt6', 'fallback_order': ['gpt6', 'deepseek-flash', 'deepseek-v4-pro'],
        'frozen_sha256': fingerprints, 'requests': [], 'results': [], 'expectations_sent': False,
        'existing_runs_modified': False, 'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
        'windows_compile': 'NOT_RUN_TEXT_CONTROL_ONLY', 'model_weight_training': False,
        'scope': 'Fixed known controls of explicit feedback handling, not a blind accuracy or whole-chapter assessment.'}
    active = {'case_id': None}

    def save():
        write_json(output / 'state.json', state)

    def before(metadata):
        if state['request_count'] >= state['request_limit']:
            raise AgentError('BUDGET_EXHAUSTED', 'Isolated fixed-control request limit reached')
        if any(digest((frozen / name).read_bytes()) != expected for name, expected in fingerprints.items()):
            raise AgentError('FROZEN_INPUT_CHANGED', 'Frozen feedback control changed')
        state['request_count'] += 1
        state['requests'].append({'type': 'request', 'number': state['request_count'], **active, **metadata})
        save()

    def record(metadata):
        state['requests'].append({'type': 'result', 'number': state['request_count'], **active, **metadata})
        save()

    save()
    try:
        for case in cases:
            active['case_id'] = case['id']
            folder = output / case['id']
            context = case['input']
            write_json(folder / 'input.json', context)
            entry = {'case_id': case['id'], 'started_at': now(), 'input_sha256': digest(context),
                     'expected_local_only': case['expected'], 'classification': 'NOT_RUN'}
            try:
                provider = CompatibleChatProvider(settings, preferred_model='gpt6', allow_fallback=True,
                    before_request=before, record=record, failure_dir=folder / 'invalid')
                response = provider.generate('reviewer_feedback', context, helper.FeedbackAssessment)
                write_json(folder / 'response.json', response)
                entry.update(response_sha256=digest(response), actual_response=provider.last_response_metadata)
                receipt, scoped_issues = helper.validate_assessment(response, context)
                write_json(folder / 'validated-receipt.json', receipt)
                write_json(folder / 'scoped-issues.json', scoped_issues)
                actual = {item['id']: item['status'] for item in receipt['items']}
                results = {identity: actual.get(identity) in (wanted if isinstance(wanted, list) else [wanted])
                    for identity, wanted in case['expected'].items()}
                passed = bool(results) and all(results.values()) and set(actual) == set(case['expected'])
                repair_targets = {item['id']: item['repair_unit_ids'] for item in receipt['items']}
                issue_targets = [item['unit_id'] for item in scoped_issues]
                actions_match = Counter(issue_targets) == Counter(target for targets in repair_targets.values() for target in targets)
                passed = passed and actions_match
                entry.update(status='VALIDATED', classification='PASS' if passed else 'FAIL',
                    observed_dispositions=actual, per_item_expected_matches=results,
                    scoped_issue_count=len(scoped_issues), repair_unit_ids=repair_targets,
                    scoped_issue_unit_ids=issue_targets, scoped_actions_match_explicit_targets=actions_match)
            except Exception as exc:
                entry.update(status='BLOCKED', classification='FAIL', error_type=type(exc).__name__,
                    error_code=getattr(exc, 'code', None), error=str(exc)[:3000])
            entry['finished_at'] = now(); state['results'].append(entry); save()
            print(json.dumps({'case_id': entry['case_id'], 'status': entry['status'],
                'classification': entry['classification'], 'requests': state['request_count']}, ensure_ascii=True), flush=True)
        state.update(status='PASS' if all(x['classification'] == 'PASS' for x in state['results']) else 'NEEDS_REVIEW', finished_at=now())
        save()
        return 0 if state['status'] == 'PASS' else 2
    finally:
        provider_module.PROMPTS = original_prompts
        save()


if __name__ == '__main__':
    raise SystemExit(main())
