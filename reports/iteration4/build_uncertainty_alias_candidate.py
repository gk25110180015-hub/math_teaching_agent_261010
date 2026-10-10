"""Recognize an audited migration as an alias of its immutable original verdict."""
import ast
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];REPORTS=Path(__file__).resolve().parent
OUT=REPORTS/'uncertainty-alias-candidate';OUT.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=ROOT/'src/math_agent/uncertainty_protocol_recovery.py';text=p.read_text(encoding='utf-8')
old="""    if len(matches) != 1:
        raise ValueError('Ambiguous prior uncertainty verdicts for the same mathematical input')
    path, state = matches[0]
"""
new="""    roots = [(path, state) for path, state in matches
             if state.get('identity', {}).get('contract') == LEGACY_CONTRACT]
    if len(roots) != 1:
        raise ValueError('Ambiguous prior uncertainty verdicts for the same mathematical input')
    path, state = roots[0]
    legacy = _replay_invalid(guard, path, state, expected_source)
    for other_path, other_state in matches:
        if other_path != path:
            _verify_migration_alias(guard, other_path, other_state, legacy)
    return legacy


def _verify_migration_alias(guard, path, state, legacy):
    # Only the two precisely known deployments differed in SSE API-error
    # transport handling. No arbitrary policy versions or new calls fold in.
    contract = {**copy.deepcopy(LEGACY_CONTRACT), 'version': 2,
        'helper_sha256': '2014e3aec411c6aced3fe0f16e38323397bbd9b5a44e0841fe1a800157511187',
        'protocol_recovery_sha256': 'fcb647c4ba2d5cfbda92485ba9a6d284eed9e4ab611f0117a76baf231d77cd15'}
    known = [{**contract, 'provider_sha256': value} for value in (
        'adaac69a8e12ff4956a8b251170176ab3cae80da787bd7f76bd729f116303685',
        '529a8c3baf3f660d503757302534caa0f89a3cdb18b7bd31b0ddf7a5dc124c79')]
    if (state.get('schema_version') != 1 or state.get('identity', {}).get('contract') not in known
            or state.get('status') != 'REVIEWED' or state.get('calls') != 1
            or state.get('provider_calls_during_replay') != 0
            or state.get('migration_source') != legacy['source']
            or state.get('origin_job_id') != legacy['origin_job_id']
            or state.get('response_file') != 'response-1.json'):
        raise ValueError('Additional uncertainty verdict is not a known completed migration alias')
    if digest(state['identity']) != state.get('identity_hash') or path.parent.name != state['identity_hash'][:24]:
        raise ValueError('Migration alias identity SHA mismatch')
    expected = {'input.json': guard.context, 'migration.json': legacy['provenance'],
        **{name: legacy[name] for name in ('ordinary-context.json', 'ordinary-review.json',
            'assessment-input.json', 'response-1.json', 'assessment.json')}}
    if set(state['dependencies']) != set(expected):
        raise ValueError('Migration alias has missing or unexpected evidence')
    for name, value in expected.items():
        raw = within(path.parent, name).read_bytes()
        if digest(raw) != state['dependencies'][name] or json.loads(raw) != value:
            raise ValueError('Migration alias evidence differs from original replay')
    receipt = {'identity_hash': state['identity_hash'], 'source': legacy['source'],
        'evidence_key': path.relative_to(guard.p.settings.workspace).as_posix(),
        'migration_sha256': state['dependencies']['migration.json'],
        'provider_calls_during_replay': 0, 'teacher_review': 'NOT_RUN'}
    found = [json.loads(row['payload_json']) for row in _events(guard.p)
        if row['type'] == 'math.uncertainty_migrated'
        and json.loads(row['payload_json']).get('identity_hash') == state['identity_hash']]
    if found != [receipt]:
        raise ValueError('Migration alias lacks its unique exact audit receipt')


def _replay_invalid(guard, path, state, expected_source):
    # The original strict replay checks remain unchanged below this boundary.
    from .domain import MathReview
    from .uncertainty_review import validate_uncertainty_assessment
"""
assert text.count(old)==1;text=text.replace(old,new,1);ast.parse(text)
target=OUT/p.name;target.write_text(text,encoding='utf-8',newline='\n')
test=REPORTS/'test_uncertainty_migration_alias.candidate.py'
files=[dict(source=p.relative_to(ROOT).as_posix(),candidate=target.relative_to(REPORTS).as_posix(),baseline_sha256=sha(p),candidate_sha256=sha(target)),
       dict(source='tests/test_uncertainty_migration_alias.py',candidate=test.name,baseline_sha256=None,candidate_sha256=sha(test))]
(OUT/'manifest.json').write_text(json.dumps({'status':'CANDIDATE_NOT_VALIDATED','files':files},indent=2),encoding='utf-8')
print('Candidate only; original verdict and deployed files unchanged')
