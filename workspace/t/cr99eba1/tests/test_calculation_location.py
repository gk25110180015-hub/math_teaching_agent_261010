"""Actual symbolic bindings plus labelled fault-injection tests for diagnostics."""
from copy import deepcopy
import subprocess

import pytest

from math_agent.calculation_protocol import calculation_protocol
from math_agent.mathcheck import check_math
import math_agent.mathcheck as module


def fixture():
    example=deepcopy(calculation_protocol()["examples"][0])
    return {"units":[example["unit"]],"calculations":[example["calculation"]]}


def assert_located(result,unit_id,calculation_id):
    assert result["evidence"]
    assert result["evidence"][0]["unit_id"]==unit_id
    assert result["evidence"][0]["calculation_id"]==calculation_id
    for issue in result["issues"]:
        if issue["location"].get("calculation_id")==calculation_id:
            assert issue["location"]["unit_id"]==unit_id


@pytest.mark.unit
def test_actual_failed_countercheck_locates_own_content_unit():
    source=fixture();request=source["calculations"][0]
    request["expected"]={"op":"Integer","value":1}
    result=check_math(source)
    assert result["status"]=="FAIL"
    assert any(i["rule_id"]=="SYMBOLIC_COUNTERCHECK_FAILED" for i in result["issues"])
    assert_located(result,request["unit_id"],request["id"])


@pytest.mark.unit
def test_actual_unknown_countercheck_keeps_unit_location():
    source=fixture();request=source["calculations"][0]
    request["assumptions"]={}
    result=check_math(source)
    assert result["status"]=="NEEDS_REVIEW"
    assert_located(result,request["unit_id"],request["id"])


@pytest.mark.unit
def test_actual_success_is_bound_and_legacy_missing_unit_id_remains_supported():
    source=fixture();request=source["calculations"][0]
    result=check_math(source)
    assert result["status"]=="PASS"
    assert_located(result,request["unit_id"],request["id"])
    del request["unit_id"]
    legacy=check_math(source)
    assert legacy["status"]=="PASS"
    assert "unit_id" not in legacy["evidence"][0]


@pytest.mark.unit
@pytest.mark.parametrize("unknown",["OTHER-SECTION.U1",None,[]])
def test_explicit_unknown_unit_is_blocked_before_any_math_execution(monkeypatch,unknown):
    source=fixture();source["calculations"][0]["unit_id"]=unknown
    def forbidden(*args,**kwargs):
        raise AssertionError("Unbound calculation must never reach the subprocess")
    monkeypatch.setattr(module.subprocess,"Popen",forbidden)
    result=check_math(source)
    assert result["status"]=="FAIL"
    assert result["evidence"][0]["evidence_type"]=="not_checked"
    issue=next(i for i in result["issues"] if i["rule_id"]=="CALCULATION_UNIT_BINDING")
    assert issue["location"]["requested_unit_id"]==unknown
    assert "unit_id" not in issue["location"],"Never tell unit-scoped repair to edit a nonexistent unit"


@pytest.mark.unit
def test_oversized_request_retains_unit_and_not_run_evidence():
    source=fixture();request=source["calculations"][0];request["oversized"]="x"*66000
    result=check_math(source)
    assert result["status"]=="FAIL"
    assert any(i["rule_id"]=="MATH_INPUT_LIMIT" for i in result["issues"])
    assert result["evidence"][0]["status"]=="NOT_RUN"
    assert_located(result,request["unit_id"],request["id"])


@pytest.mark.unit
def test_non_json_request_is_located_without_crashing():
    source=fixture();request=source["calculations"][0];request["unexpected_set"]={1,2}
    result=check_math(source)
    assert result["status"]=="FAIL"
    assert any(i["rule_id"]=="MATH_INPUT_INVALID" for i in result["issues"])
    assert_located(result,request["unit_id"],request["id"])


@pytest.mark.unit
def test_subprocess_start_failure_is_located_fault_injection(monkeypatch):
    source=fixture();request=source["calculations"][0]
    def failed(*args,**kwargs):raise OSError("synthetic process start failure")
    monkeypatch.setattr(module.subprocess,"Popen",failed)
    result=check_math(source)
    assert result["status"]=="NEEDS_REVIEW"
    assert_located(result,request["unit_id"],request["id"])


@pytest.mark.unit
def test_per_request_timeout_is_located_fault_injection(monkeypatch):
    import math_agent.compiler as compiler
    source=fixture();request=source["calculations"][0];terminated=[]
    class TimedOut:
        def communicate(self,payload,timeout):
            assert timeout==8
            raise subprocess.TimeoutExpired("synthetic-math-child",timeout)
    process=TimedOut()
    monkeypatch.setattr(module.subprocess,"Popen",lambda *a,**k:process)
    monkeypatch.setattr(compiler,"terminate_tree",lambda child:terminated.append(child))
    result=check_math(source)
    assert result["status"]=="NEEDS_REVIEW" and terminated==[process]
    assert_located(result,request["unit_id"],request["id"])


@pytest.mark.unit
def test_total_budget_marks_each_unexecuted_request_with_location(monkeypatch):
    source=fixture();second=deepcopy(source["calculations"][0]);second["id"]="SECOND.C2";source["calculations"].append(second)
    ticks=iter([0,61,62]);monkeypatch.setattr(module.time,"monotonic",lambda:next(ticks))
    result=check_math(source)
    assert result["status"]=="NEEDS_REVIEW"
    assert {e["calculation_id"] for e in result["evidence"]}=={c["id"] for c in source["calculations"]}
    assert all(e["status"]=="NOT_RUN" and e["unit_id"]==source["units"][0]["id"] for e in result["evidence"])
