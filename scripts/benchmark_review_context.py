"""Opt-in four-control review calibration; frozen prompts, six requests maximum."""
import argparse
import copy
import json
import re
from pathlib import Path

import math_agent.provider as provider_module
from math_agent.domain import MathReview
from math_agent.provider import CompatibleChatProvider
from math_agent.settings import PROJECT_ROOT, Settings
from math_agent.util import AgentError, digest, now, scrub, write_json

FIXTURES = PROJECT_ROOT / 'reports/iteration2/review-context-calibration-fixtures.json'
REQUEST_LIMIT = 6


def classify(review, case):
    """Expectations are evaluated locally after receiving the model response."""
    actual = set(case['input']['actual_unit_ids'])
    checked = review['checked_unit_ids']
    coverage = set(checked) == actual and len(checked) == len(actual)
    valid_ids = all(item['unit_id'] in actual for item in review['issues'])
    flagged = {item['unit_id'] for item in review['issues']
               if item['severity'] in ('blocking', 'review')}
    blocking = {item['unit_id'] for item in review['issues'] if item['severity'] == 'blocking'}
    expectation = case['expectation']
    if expectation['kind'] == 'CORRECT_CONTROL':
        decision = not flagged
    else:
        decision = (set(expectation.get('expected_flagged_unit_ids', [])).issubset(flagged)
                    and set(expectation.get('expected_blocking_unit_ids', [])).issubset(blocking))
        if expectation.get('expected_flagged_any_of'):
            decision &= bool(flagged.intersection(expectation['expected_flagged_any_of']))
        if expectation.get('expected_blocking_any_of'):
            decision &= bool(blocking.intersection(expectation['expected_blocking_any_of']))
    return {'classification_status': 'PASS' if coverage and valid_ids and decision else 'FAIL',
            'coverage_complete': coverage, 'issue_ids_valid': valid_ids,
            'flagged_unit_ids': sorted(flagged), 'blocking_unit_ids': sorted(blocking),
            'expectation_matched': bool(decision)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-live', action='store_true', help='Explicitly enable real requests; environment configuration is also required.')
    parser.add_argument('--output-dir', type=Path, required=True, help='A NEW directory below the project reports directory.')
    parser.add_argument('--prompt-file', type=Path, help='Local UTF-8 reviewer prompt; defaults to the current product prompt. Always snapshotted first.')
    parser.add_argument('--expected-prompt-version', type=int, help='Refuse an unexpected declared prompt version.')
    args = parser.parse_args(argv)
    root = args.output_dir.resolve()
    if not root.is_relative_to((PROJECT_ROOT / 'reports').resolve()) or root == (PROJECT_ROOT / 'reports').resolve():
        parser.error('--output-dir must be a new child directory of project reports')
    if root.exists():
        parser.error('--output-dir already exists; previous evidence must be preserved')
    prompt_path = (args.prompt_file or provider_module.PROMPTS / 'reviewer_math.md').resolve()
    if not prompt_path.is_file():
        parser.error('--prompt-file must name an existing local UTF-8 file')
    prompt_bytes = prompt_path.read_bytes()
    try:
        prompt_bytes.decode('utf-8')
    except UnicodeDecodeError:
        parser.error('--prompt-file must be UTF-8')
    # Match TextIO universal-newline reading used by the production provider.
    prompt_text = prompt_path.read_text(encoding='utf-8')
    version_match = re.match(r'^\ufeff?版本\s*(\d+)\b', prompt_text)
    version = int(version_match.group(1)) if version_match else None
    if args.expected_prompt_version is not None and version != args.expected_prompt_version:
        parser.error('declared prompt version differs from --expected-prompt-version')
    fixture_bytes = FIXTURES.read_bytes()
    fixtures = json.loads(fixture_bytes)
    cases = fixtures['cases']
    if len(cases) != 4 or len({case['id'] for case in cases}) != 4:
        parser.error('the calibration requires four uniquely identified controls')
    if not args.execute_live:
        print(json.dumps({'status': 'NOT_RUN', 'reason': 'Requires --execute-live and environment configuration',
                          'case_count': len(cases), 'request_limit': REQUEST_LIMIT,
                          'prompt_version': version, 'prompt_sha256': digest(prompt_bytes),
                          'output_created': False}, ensure_ascii=True))
        return 0
    settings = Settings().model_copy(update={'max_network_retries': 0, 'max_schema_repair_attempts': 1})
    if not settings.live_api_enabled or not settings.api_key.get_secret_value():
        parser.error('MATH_AGENT_LIVE_API_ENABLED and MATH_AGENT_API_KEY environment configuration required')
    root.mkdir(parents=True, exist_ok=False)
    snapshot_dir = root / 'prompt-snapshot'
    snapshot_dir.mkdir()
    snapshot = snapshot_dir / 'reviewer_math.md'
    snapshot.write_bytes(prompt_bytes)
    (root / 'fixtures-local-only.json').write_bytes(fixture_bytes)
    write_json(root / 'schema.json', MathReview.model_json_schema())
    original_prompts = provider_module.PROMPTS
    provider_module.PROMPTS = snapshot_dir
    state = {'created_at': now(), 'status': 'RUNNING', 'request_count': 0, 'request_limit': REQUEST_LIMIT,
             'network_retries': 0, 'schema_repair_attempts_per_case': 1,
             'model': settings.model, 'api_base_url': settings.api_base_url,
             'streaming': settings.llm_streaming, 'prompt_source': str(prompt_path),
             'prompt_version': version, 'prompt_snapshot_before_sha256': digest(snapshot.read_bytes()),
             'prompt_text_hash': digest(prompt_text), 'schema_hash': digest(MathReview.model_json_schema()),
             'fixture_sha256': digest(fixture_bytes), 'script_sha256': digest(Path(__file__).read_bytes()),
             'provider_sha256': digest(Path(provider_module.__file__).read_bytes()),
             'records': [], 'cases': [], 'teacher_review': 'NOT_RUN',
             'original_runs_mutated': False, 'expectations_sent': False}
    current = {'case': None, 'messages': None, 'request_number': None}

    def save():
        write_json(root / 'state.json', state)

    def verify_snapshot():
        if digest(snapshot.read_bytes()) != state['prompt_snapshot_before_sha256']:
            raise AgentError('PROMPT_SNAPSHOT_CHANGED', 'Calibration prompt snapshot changed; no further request permitted')

    def before(metadata):
        verify_snapshot()
        if metadata.get('prompt_hash') != state['prompt_text_hash'] or metadata.get('schema_hash') != state['schema_hash']:
            raise AgentError('REQUEST_IDENTITY_MISMATCH', 'Actual request prompt/schema differs from frozen snapshot')
        if metadata.get('input_hash') != digest(current['messages']):
            raise AgentError('REQUEST_IDENTITY_MISMATCH', 'Actual messages differ from request archive')
        if state['request_count'] >= REQUEST_LIMIT:
            raise AgentError('BUDGET_EXHAUSTED', 'Calibration six-request hard limit exhausted')
        state['request_count'] += 1
        number = state['request_count']
        current['request_number'] = number
        payload = {'model': settings.model, 'messages': current['messages'], 'temperature': metadata['temperature']}
        if settings.llm_streaming:
            payload['stream'] = True
        archive = {'request_number': number, 'case': current['case'], 'metadata': metadata,
                   'url': settings.api_base_url.rstrip('/') + '/chat/completions',
                   'json_body': payload, 'authorization_archived': False}
        write_json(root / f'request-{number:02d}.json', archive)
        state['records'].append({'type': 'request', 'case': current['case'], 'request_number': number, **metadata})
        save()  # Count persisted before transmission; never erase a failed or uncertain request.

    def record(metadata):
        state['records'].append({'type': 'result', 'case': current['case'],
                                 'request_number': current['request_number'], **metadata})
        save()

    class RecordingProvider(CompatibleChatProvider):
        async def _request(self, messages, role, *, prompt_metadata=None, model_id=None, allow_fallback=None):
            current['messages'] = copy.deepcopy(messages)
            result = await super()._request(messages, role, prompt_metadata=prompt_metadata,
                model_id=model_id, allow_fallback=allow_fallback)
            # This is the provider-returned model text, not a claim to capture raw HTTP/SSE bytes.
            safe_text = scrub(result)
            path = root / f'response-{current["request_number"]:02d}-model-text.txt'
            path.write_bytes(safe_text.encode('utf-8'))
            state['records'].append({'type': 'model_text', 'request_number': current['request_number'],
                                     'case': current['case'], 'sha256': digest(path.read_bytes()),
                                     'raw_http_archived': False, 'provider_scrubbed_text': True})
            save()
            return result

    # This historical calibration compares one requested model; failover would
    # change the subject and make its fixed-model request archives misleading.
    provider = RecordingProvider(settings, before_request=before, record=record,
        failure_dir=root / 'provider-failures', allow_fallback=False)
    save()
    try:
        for case in cases:
            current.update(case=case['id'], messages=None, request_number=None)
            folder = root / case['id']
            folder.mkdir()
            context = copy.deepcopy(case['input'])
            write_json(folder / 'model-input.json', context)
            write_json(folder / 'local-expectation-not-sent.json', case['expectation'])
            if state['request_count'] >= REQUEST_LIMIT:
                result = {'case': case['id'], 'execution_status': 'NOT_RUN_BUDGET', 'classification_status': 'NOT_EVALUATED'}
            else:
                try:
                    verify_snapshot()
                    review = provider.generate('reviewer_math', context, MathReview)
                    write_json(folder / 'response.json', review)
                    result = {'case': case['id'], 'execution_status': 'COMPLETED', **classify(review, case)}
                except Exception as error:
                    result = {'case': case['id'], 'execution_status': 'ERROR', 'classification_status': 'NOT_EVALUATED',
                              'error_type': type(error).__name__, 'error_code': getattr(error, 'code', None),
                              'message': scrub(str(error))}
            write_json(folder / 'result.json', result)
            state['cases'].append(result)
            save()
    finally:
        provider_module.PROMPTS = original_prompts
        state['completed_at'] = now()
        state['prompt_snapshot_after_sha256'] = digest(snapshot.read_bytes())
        state['prompt_snapshot_unchanged'] = state['prompt_snapshot_before_sha256'] == state['prompt_snapshot_after_sha256']
        state['status'] = 'PASS' if (len(state['cases']) == 4 and state['prompt_snapshot_unchanged']
                                    and all(c['classification_status'] == 'PASS' for c in state['cases'])) else 'NEEDS_REVIEW'
        save()
        summary = {key: state[key] for key in ('status', 'request_count', 'request_limit', 'cases', 'prompt_version',
                    'prompt_text_hash', 'prompt_snapshot_before_sha256', 'prompt_snapshot_after_sha256', 'schema_hash', 'teacher_review')}
        summary['request_outcomes'] = [r for r in state['records'] if r['type'] == 'result' and
                                       ('elapsed_seconds' in r or r.get('status') == 'TOTAL_TIMEOUT')]
        summary['limitations'] = [
            'Four authored controls for prompt/context calibration, not an independent accuracy estimate.',
            'Expected answers, case labels and rationales were evaluated locally and never sent.',
            'Reported usage preserved per actual request; missing usage and all prices remain unknown.',
            'Provider-returned model text is archived; raw HTTP/SSE bytes and failed HTTP response bodies are not captured.',
            'No product prompt, real run, approval, counter, TeX output or teacher decision changed.']
        write_json(root / 'summary.json', summary)
    print(json.dumps({'status': state['status'], 'requests': state['request_count'],
                      'report': str(root / 'summary.json')}, ensure_ascii=True))
    return 0 if state['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
