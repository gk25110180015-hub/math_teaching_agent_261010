import pytest
from pydantic import ValidationError
from math_agent.domain import LectureProposal
from math_agent.provider import MockProvider

def proposal():
    return MockProvider().generate('planner_lecture',{'topic':'数列极限'},LectureProposal)

def test_section_prerequisites_must_be_ids_and_prior_sections():
    p=proposal();p['sections'][0]['prerequisites']=['实数基本运算']
    with pytest.raises(ValidationError):LectureProposal.model_validate(p)
    p=proposal();p['sections'][0]['prerequisites']=['S02']
    with pytest.raises(ValidationError):LectureProposal.model_validate(p)

def test_section_ids_cannot_repeat():
    p=proposal();p['sections'][1]['id']='S01'
    with pytest.raises(ValidationError):LectureProposal.model_validate(p)

def test_global_prerequisites_remain_natural_language():
    p=proposal();p['prerequisites']=['实数基本运算']
    assert LectureProposal.model_validate(p).prerequisites==['实数基本运算']

def test_reference_declarations_are_unique_across_sections():
    p=proposal()
    p['sections'][0]['reference_labels']=['S01_limit_definition']
    p['sections'][1]['reference_labels']=['S01_limit_definition']
    with pytest.raises(ValidationError):LectureProposal.model_validate(p)
