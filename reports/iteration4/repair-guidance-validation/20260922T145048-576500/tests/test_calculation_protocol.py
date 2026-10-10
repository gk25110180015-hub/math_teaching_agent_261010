"""Protocol examples execute real local SymPy subprocesses; no API/mocked calculator."""
from copy import deepcopy
import json

import pytest

from math_agent.calculation_protocol import calculation_protocol
from math_agent.domain import WrittenSection
from math_agent.mathcheck import check_math


def section(example):
    return WrittenSection.model_validate({"section_id":"PROTOCOL-EXAMPLES","units":[example["unit"]],"calculations":[example["calculation"]],"uncertainties":[]}).model_dump()


@pytest.mark.unit
def test_protocol_is_serializable_fresh_and_bound_to_supported_requests():
    protocol=calculation_protocol()
    assert json.loads(json.dumps(protocol,ensure_ascii=False,allow_nan=False))==protocol
    assert {e["calculation"]["kind"] for e in protocol["examples"]}=={"limit","series","derivative"}
    for example in protocol["examples"]:
        assert example["calculation"]["unit_id"]==example["unit"]["id"]
        assert "assumptions" in example["calculation"]
        section(example)
    protocol["examples"][0]["calculation"]["kind"]="python"
    assert calculation_protocol()["examples"][0]["calculation"]["kind"]=="limit"


@pytest.mark.unit
@pytest.mark.parametrize("kind",["limit","series","derivative"])
def test_protocol_example_passes_actual_json_ast_calculation(kind):
    example=next(e for e in calculation_protocol()["examples"] if e["calculation"]["kind"]==kind)
    result=check_math(section(example))
    assert result["status"]=="PASS",result
    assert len(result["evidence"])==1
    evidence=result["evidence"][0]
    assert evidence["status"]=="PASS" and evidence["evidence_type"]=="symbolic_check_passed"
    assert evidence["tool"]=="SymPy" and evidence["tool_version"]
    assert evidence["calculation_id"]==example["calculation"]["id"]
    assert evidence["result"]==example["expected_result"]


@pytest.mark.unit
def test_log_derivative_does_not_pass_after_required_domain_is_removed():
    example=next(e for e in calculation_protocol()["examples"] if e["calculation"]["kind"]=="derivative")
    example["calculation"]["assumptions"]={"x":{"real":True}}
    result=check_math(section(example))
    assert result["status"]=="NEEDS_REVIEW"
    assert result["evidence"][0]["evidence_type"]=="not_checked"
    assert result["evidence"][0]["domain_requirements"]


@pytest.mark.unit
def test_undeclared_symbol_does_not_turn_into_pass():
    example=deepcopy(calculation_protocol()["examples"][0])
    example["calculation"]["assumptions"]={}
    result=check_math(section(example))
    assert result["status"]=="NEEDS_REVIEW"
    assert result["evidence"][0]["evidence_type"]=="not_checked"


@pytest.mark.unit
def test_numeric_example_is_review_evidence_not_symbolic_proof():
    unit={"id":"NUMERIC.U1","kind":"explanation","tex":r"在 $x=1,2$ 抽查两个表达式。","relates_to":None}
    request={"id":"NUMERIC.C1","unit_id":unit["id"],"kind":"numeric_spotcheck","assumptions":{"x":{"real":True}},"lhs":{"op":"Pow","args":[{"op":"Symbol","name":"x"},{"op":"Integer","value":2}]},"rhs":{"op":"Mul","args":[{"op":"Symbol","name":"x"},{"op":"Symbol","name":"x"}]},"points":[{"x":1},{"x":2}]}
    result=check_math({"units":[unit],"calculations":[request]})
    assert result["status"]=="NEEDS_REVIEW"
    assert result["evidence"][0]["evidence_type"]=="numeric_spotcheck_passed"
    assert any(i["rule_id"]=="NUMERIC_IS_NOT_PROOF" for i in result["issues"])
