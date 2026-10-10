"""Offline provenance of the real S03 note appended by the fifth local patch."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from math_agent.calculation_review_context import calculation_review_sources
from math_agent.local_patch import apply_local_patch
from math_agent.mathcheck import check_math
from math_agent.uncertainty_review import build_uncertainty_context, declared_doubts
from math_agent.util import AgentError, canonical, digest
from test_calculation_review_context import build, fixture_recovery, offline_environment, registered_source


CAPTURE = Path(__file__).parent / 'fixtures' / 'calculation_declaration_history'
BEFORE = '070479dfd8488adce65a251a'
AFTER = 'dc62587a164569aef546752b'


def captured(name):
    return json.loads((CAPTURE / name).read_bytes())


def origin_fixture(tmp_path, *, pin=True, after=True):
    recovery, _, _ = fixture_recovery(tmp_path)
    recovery.p.build_root = recovery.p.settings.workspace / 'b/frozen-build'
    recovery.p.build_root.mkdir(parents=True)
    for guard_id, names in ((BEFORE, ('input.json', 'state.json', 'ordinary-context.json', 'ordinary-review.json')),
                            (AFTER, ('input.json', 'state.json'))):
        if guard_id == AFTER and not after:
            continue
        folder = recovery.p.root / 'uncertainty-reviews' / guard_id
        folder.mkdir(parents=True)
        for name in names:
            shutil.copyfile(CAPTURE / guard_id / name, folder / name)
    patch = recovery.p.build_root / 'repair-5-patch.json'
    shutil.copyfile(CAPTURE / patch.name, patch)
    dependency = {'key': patch.relative_to(recovery.p.settings.workspace).as_posix(),
                  'hash': digest(patch.read_bytes()), 'error_code': 'LOCAL_REPAIR_CACHE_INVALID'}
    recovery.state['evidence_dependencies'] = [dependency] if pin else []
    section = captured('current-candidate.json')
    return recovery, section, check_math(section), patch


def origins(packet):
    return packet['corrections'][0].get('declaration_origins', [])


def test_real_appended_note_has_exact_pinned_patch_and_replayable_before_after_review_chain(tmp_path):
    recovery, section, math, patch_path = origin_fixture(tmp_path)
    original = copy.deepcopy((section, math, recovery.state))
    archived = {path: path.read_bytes() for path in recovery.p.root.rglob('*.json')}
    packet = build(recovery, section, math)
    assert len(origins(packet)) == 1
    origin = origins(packet)[0]
    patch = captured('repair-5-patch.json')
    note = patch['uncertainties_append'][0]
    declaration = next(item for item in declared_doubts(section) if item['original_text'] == note)
    assert origin['declaration'] == declaration and declaration['unit_id'] is None
    assert origin['patch']['content'] == patch
    assert origin['patch']['sha256'] == digest(patch_path.read_bytes())
    assert (recovery.p.settings.workspace / origin['patch']['key']).resolve() == patch_path.resolve()
    before = captured(BEFORE + '/input.json')['section']
    after = captured(AFTER + '/input.json')['section']
    reproduced, _ = apply_local_patch(before, ['S03.U07'], patch)
    assert reproduced == after
    assert origin['before_section_hash'] == digest(before) and origin['after_section_hash'] == digest(after)
    assert note not in before['uncertainties'] and note in after['uncertainties']
    assert origin['prior_unresolved_issues'] == captured(BEFORE + '/ordinary-context.json')['local_recovery']['unresolved_issues']
    assert origin['ordinary_issues'] == captured(BEFORE + '/ordinary-review.json')['issues']
    assert 'S03.C01' in canonical(origin['ordinary_issues']) and '29/28' in canonical(origin['ordinary_issues'])
    for source_name in ('before_source', 'after_source'):
        source = origin[source_name]
        assert digest((recovery.p.settings.workspace / source['input_key']).read_bytes()) == source['input_sha256']
    for source_name in ('ordinary_context_source', 'ordinary_review_source'):
        source = origin[source_name]
        assert digest((recovery.p.settings.workspace / source['key']).read_bytes()) == source['sha256']
    assert original == (section, math, recovery.state)
    assert all(path.read_bytes() == raw for path, raw in archived.items())
    assert any(issue['rule_id'] == 'DECLARED_MATH_UNCERTAINTY' for issue in math['issues'])


@pytest.mark.parametrize('damage', ['pinned_patch', 'frozen_review'])
def test_origin_integrity_damage_blocks_instead_of_inventing_a_note_history(tmp_path, damage):
    recovery, section, math, patch = origin_fixture(tmp_path)
    target = patch if damage == 'pinned_patch' else recovery.p.root / 'uncertainty-reviews' / BEFORE / 'ordinary-review.json'
    target.write_bytes(b'{}')
    with pytest.raises(AgentError) as error:
        build(recovery, section, math)
    assert error.value.code == 'UNCERTAINTY_EVIDENCE_BLOCKED'


def test_identical_note_is_not_inferred_from_an_unpinned_patch(tmp_path):
    recovery, section, math, _ = origin_fixture(tmp_path, pin=False)
    packet = build(recovery, section, math)
    assert packet and not origins(packet)
    assert captured('repair-5-patch.json')['uncertainties_append'][0] in section['uncertainties']


def test_note_origin_requires_a_registered_exact_after_candidate(tmp_path):
    recovery, section, math, _ = origin_fixture(tmp_path, after=False)
    packet = build(recovery, section, math)
    assert packet and not origins(packet)


def test_similar_current_note_is_not_assigned_an_exact_historical_origin(tmp_path):
    recovery, section, _, _ = origin_fixture(tmp_path)
    note = captured('repair-5-patch.json')['uncertainties_append'][0]
    index = section['uncertainties'].index(note)
    section['uncertainties'][index] += ' 这是另外追加的独立限定。'
    packet = build(recovery, section, check_math(section))
    assert packet and not origins(packet)


def test_duplicate_after_archives_do_not_duplicate_origins_and_sources_include_the_full_chain(tmp_path):
    recovery, section, math, _ = origin_fixture(tmp_path)
    duplicate = captured(AFTER + '/input.json')
    duplicate['deterministic_issues'].append({'severity': 'warning', 'message': 'Same accepted after body in another frozen context.'})
    registered_source(recovery, duplicate)
    packet = build(recovery, section, math)
    assert len(origins(packet)) == 1
    assert build(recovery, section, math) == packet
    before = copy.deepcopy(packet)
    sources = calculation_review_sources(packet)
    assert len(sources) == 1 and sources == calculation_review_sources(copy.deepcopy(packet))
    assert sources[0]['source_sha256'] == digest(sources[0]['tex'])
    origin = origins(packet)[0]
    assert origin['declaration']['original_text'] in sources[0]['tex']
    assert canonical(origin['patch']['content']) in sources[0]['tex']
    assert canonical(origin['ordinary_issues']) in sources[0]['tex']
    assert packet == before


def test_enriched_current_guard_and_changed_pending_state_do_not_recursively_change_packet(tmp_path):
    recovery, section, math, _ = origin_fixture(tmp_path)
    packet = build(recovery, section, math)
    assert len(origins(packet)) == 1
    context = build_uncertainty_context(recovery.p.run['plan'], section, [], math, math['issues'])
    context['calculation_recovery_evidence'] = copy.deepcopy(packet)
    context['sources'].extend(calculation_review_sources(packet))
    current_guard = registered_source(recovery, context)
    current_bytes = {path: path.read_bytes() for path in current_guard.iterdir() if path.is_file()}
    recovery.state.update(phase='NEEDS_REPAIR', proposal_calls=101,
        pending_issues=[{'severity': 'review', 'message': '保留声明来源的待核实问题。', 'prior_packet': copy.deepcopy(packet)}])
    assert build(recovery, section, math) == packet
    assert build(recovery, section, math) == packet
    assert all(path.read_bytes() == raw for path, raw in current_bytes.items())
    assert 'prior_packet' not in canonical(packet)
