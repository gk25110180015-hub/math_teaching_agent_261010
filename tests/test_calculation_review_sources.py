"""Offline citation contract for verified historical/current calculation facts."""
import copy

import pytest

from math_agent.calculation_review_context import calculation_review_sources
from math_agent.uncertainty_review import build_uncertainty_context, validate_uncertainty_assessment
from math_agent.util import canonical, digest
from test_calculation_review_context import build, fixture_recovery, offline_environment
from test_independent_calculation_repair import CalculationProvider
from test_local_recovery import setup


@pytest.fixture(scope='module')
def bundle(tmp_path_factory):
    recovery, section, math = fixture_recovery(tmp_path_factory.mktemp('citable'))
    packet = build(recovery, section, math)
    sources = calculation_review_sources(packet)
    context = build_uncertainty_context(recovery.p.run['plan'], section, [], math, math['issues'])
    context['calculation_recovery_evidence'] = copy.deepcopy(packet)
    context['sources'].extend(copy.deepcopy(sources))
    return recovery, packet, sources, context


def cited_assessment(context):
    calc_source = next(source for source in context['sources'] if source['source_key'].startswith('calculation:'))
    items = []
    for note in context['declared_doubts']:
        body = next(source for source in context['sources']
                    if source['source_key'] == 'current:' + (note['unit_id'] or 'S03.U07'))
        items.append({'uncertainty_id': note['uncertainty_id'], 'unit_id': note['unit_id'],
            'disposition': 'resolved_by_current_body',
            'reason': '离线受控审阅同时引用当前实际正文和已复现的历史核算来源，不代表教师验收。',
            'evidence': [{'source_key': source['source_key'], 'source_sha256': source['source_sha256'], 'quote': source['tex']}
                         for source in (body, calc_source)],
            'remaining_dependency': False, 'repair_instruction': None})
    return {'items': items, 'limitations': ['Injected citation validation only, not teacher acceptance.']}


def test_complete_chinese_sources_are_hashed_stable_and_preserve_packet_and_archive(bundle):
    recovery, packet, sources, _ = bundle
    original = copy.deepcopy(packet)
    archived = {path: path.read_bytes() for path in recovery.p.root.rglob('*.json')}
    assert calculation_review_sources(None) == []
    assert calculation_review_sources(packet) == calculation_review_sources(copy.deepcopy(packet)) == sources
    assert len(sources) == len(packet['corrections']) == 1
    source, correction = sources[0], packet['corrections'][0]
    assert source['source_key'].startswith('calculation:') and not source['source_key'].startswith('current:')
    assert source['unit_id'] == correction['unit_id'] == 'S03.U07'
    assert source['source_sha256'] == digest(source['tex'])
    assert '历史完整请求' in source['tex'] and '当前完整请求' in source['tex']
    for key in ('previous_request', 'current_request', 'previous_evidence', 'reproduced_previous_evidence', 'current_evidence', 'source'):
        assert canonical(correction[key]) in source['tex']
    assert '29/28' in source['tex'] and '27/28' in source['tex']
    assert packet == original
    assert all(path.read_bytes() == raw for path, raw in archived.items())


def test_original_strict_validator_accepts_exact_body_and_registered_calculation_citations(bundle):
    _, _, _, context = bundle
    result = validate_uncertainty_assessment(cited_assessment(context), context)
    assert all(item['disposition'] == 'resolved_by_current_body' for item in result['items'])
    assert all(any(evidence['source_key'].startswith('current:') for evidence in item['evidence']) for item in result['items'])
    assert all(any(evidence['source_key'].startswith('calculation:') for evidence in item['evidence']) for item in result['items'])


@pytest.mark.parametrize('damage', ['source_key', 'source_sha256', 'quote'])
def test_tampered_calculation_citation_is_rejected_by_unchanged_validator(bundle, damage):
    _, _, _, context = bundle
    response = cited_assessment(context)
    evidence = response['items'][0]['evidence'][-1]
    evidence[damage] = {'source_key': 'calculation:unregistered', 'source_sha256': '0' * 64,
                        'quote': '这段伪造的历史核算推理并不存在于所提供的已注册来源。'}[damage]
    with pytest.raises(ValueError, match='exact nonempty span'):
        validate_uncertainty_assessment(response, context)


@pytest.mark.parametrize('located', [True, False])
def test_calculation_source_cannot_replace_required_current_body_evidence(bundle, located):
    _, _, _, context = bundle
    response = cited_assessment(context)
    item = next(item for item in response['items'] if bool(item['unit_id']) is located)
    item['evidence'] = [evidence for evidence in item['evidence'] if evidence['source_key'].startswith('calculation:')]
    with pytest.raises(ValueError, match='actual target evidence|actual current-body evidence'):
        validate_uncertainty_assessment(response, context)


def test_pipeline_registers_same_sources_for_both_reviewers_and_accepts_actual_citation(tmp_path, monkeypatch):
    provider = CalculationProvider()
    generate = provider.generate
    def cite_registered_source(role, context, schema):
        result = generate(role, context, schema)
        if role == 'reviewer_uncertainty' and context.get('calculation_recovery_evidence'):
            source = next(source for source in context['sources'] if source['source_key'].startswith('calculation:'))
            result['items'][0]['evidence'].append({'source_key': source['source_key'],
                'source_sha256': source['source_sha256'], 'quote': source['tex']})
        return result
    provider.generate = cite_registered_source
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    completed, reports = pipeline.lecture(plan)
    assert completed and len(compiled) == 1
    ordinary, uncertainty = provider.ordinary[-1], provider.dispositions[-1]
    expected = calculation_review_sources(ordinary['calculation_recovery_evidence'])
    assert ordinary['sources'] == expected
    assert [source for source in uncertainty['sources'] if source['source_key'].startswith('calculation:')] == expected
    assert ordinary['calculation_recovery_evidence'] == uncertainty['calculation_recovery_evidence']
    assessment = reports[0]['uncertainty_review']['assessment']
    assert validate_uncertainty_assessment(assessment, uncertainty) == assessment
    assert any(evidence['source_key'] == expected[0]['source_key'] for evidence in assessment['items'][0]['evidence'])
    assert len(provider.ordinary) == len(provider.dispositions) == 2 and len(provider.patches) == 1
