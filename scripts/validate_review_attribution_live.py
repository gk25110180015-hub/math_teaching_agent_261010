"""Opt-in, frozen two-case real API test of evidence attribution adjudication.

Uses the ordinary provider and fallback order. Does not modify chapter runs,
approved plans, teaching files or teacher reviews. Expectations stay local.
"""
import argparse
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
    parser.add_argument('--helper-file', type=Path, default=PROJECT_ROOT / 'reports/iteration4/review-evidence-attribution.candidate.py')
    parser.add_argument('--prompt-file', type=Path, default=PROJECT_ROOT / 'reports/iteration4/review_evidence_attribution.candidate.md')
    parser.add_argument('--fixtures-file', type=Path, default=PROJECT_ROOT / 'reports/iteration4/review-evidence-attribution-fixtures.json')
    args = parser.parse_args()
    if not args.execute_live:
        print('NOT_RUN: explicit --execute-live and configured environment required.')
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
    paths = {'helper.py': args.helper_file, 'review_evidence_attribution.md': args.prompt_file,
             'fixtures-local-only.json': args.fixtures_file}
    fingerprints = {}
    for name, source in paths.items():
        data = source.read_bytes(); (frozen / name).write_bytes(data)
        fingerprints[name] = digest(data)
    spec = importlib.util.spec_from_file_location('frozen_attribution_helper', frozen / 'helper.py')
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    cases = json.loads((frozen / 'fixtures-local-only.json').read_bytes())['cases']
    original_prompts = provider_module.PROMPTS
    provider_module.PROMPTS = frozen
    state = {'created_at': now(), 'status': 'RUNNING', 'request_count': 0, 'request_limit': 12,
        'preferred_model': 'gpt6', 'fallback_order': ['gpt6', 'deepseek-flash', 'deepseek-v4-pro'],
        'frozen_sha256': fingerprints, 'requests': [], 'results': [], 'expectations_sent': False,
        'existing_runs_modified': False, 'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
        'windows_compile': 'NOT_RUN_NOT_PART_OF_TEXT_CONTROLS', 'model_weight_training': False,
        'scope': 'Two known targeted controls; first uses reduced archived context, not an exact full chapter replay or blind accuracy estimate.'}
    active = {'case_id': None}

    def save():
        write_json(output / 'state.json', state)

    def before(metadata):
        if state['request_count'] >= state['request_limit']:
            raise AgentError('BUDGET_EXHAUSTED', 'Isolated control request limit reached')
        for name, expected in fingerprints.items():
            if digest((frozen / name).read_bytes()) != expected:
                raise AgentError('FROZEN_INPUT_CHANGED', 'Frozen adjudication evidence changed')
        state['request_count'] += 1
        state['requests'].append({'type': 'request', 'number': state['request_count'], **active, **metadata})
        save()

    def record(metadata):
        state['requests'].append({'type': 'result', 'number': state['request_count'], **active, **metadata})
        save()

    save()
    try:
        for case in cases:
            active['case_id'] = case['case_id']
            folder = output / case['case_id']
            original = case['original_review']
            units, prior = case['units'], case['prior_sections']
            conflicts = helper.detect_attribution_conflicts(original, units, prior)
            catalog = helper.unit_catalog(units, prior)
            assert len(conflicts) == 1, 'Fixed control must have exactly one attribution trigger'
            review_context = {'units': units, 'prior_sections': prior, 'actual_unit_ids': [u['id'] for u in units]}
            payload = {'original_review': original, 'conflicts': conflicts,
                'actual_unit_ids': review_context['actual_unit_ids'], 'review_context': review_context,
                'provided_unit_catalog': list(catalog.values()),
                'instruction': 'Resolve each original issue explicitly. A positive quote ownership conflict does not prove the mathematical criticism false. Preserve legitimate cross-unit dependency errors. Every disposition needs verbatim actual target and located source spans. A withdrawal needs target counterevidence and a reason that addresses the entire original claim. Do not add issues, reassign issues outside original targets, alter the plan or approve content.'}
            write_json(folder / 'input.json', payload)
            entry = {'case_id': case['case_id'], 'started_at': now(), 'input_sha256': digest(payload),
                     'expected_local_only': case['expected'], 'classification': 'NOT_RUN'}
            try:
                provider = CompatibleChatProvider(settings, preferred_model='gpt6', allow_fallback=True,
                    before_request=before, record=record, failure_dir=folder / 'invalid')
                response = provider.generate('review_evidence_attribution', payload, helper.AttributionAdjudication)
                write_json(folder / 'response.json', response)
                entry.update(response_sha256=digest(response), actual_response=provider.last_response_metadata)
                effective, validated = helper.validate_adjudication(original, conflicts, response, catalog)
                write_json(folder / 'effective-review.json', effective)
                write_json(folder / 'validated-dispositions.json', validated)
                expected = case['expected']; decision = validated['decisions'][0]
                allowed = expected.get('allowed_dispositions', [expected.get('disposition')])
                target = conflicts[0]['target_unit_id']
                remaining = any(i['unit_id'] == target and i['severity'] in ('review', 'blocking') for i in effective['issues'])
                original_other = [i for n, i in enumerate(original['issues']) if n != conflicts[0]['issue_index']]
                other_preserved = all(i in effective['issues'] for i in original_other)
                passed = decision['disposition'] in allowed and remaining == expected['remaining_target_blocking'] and other_preserved
                entry.update(status='VALIDATED', classification='PASS' if passed else 'FAIL',
                    disposition=decision['disposition'], remaining_target_blocking=remaining,
                    other_original_issues_preserved=other_preserved)
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
