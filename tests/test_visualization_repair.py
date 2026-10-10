import copy

import pytest

from math_agent.util import AgentError
from math_agent.visualization.generation import apply_repair, generate_program
from math_agent.visualization.models import ProgramRepair


def program():
    return {'runtime_version':2,
        'code':"function draw(ctx,t,p){ const x=p.x; const f=x*x*x-3*x; const d=3*x*x-3; ctx.fillRect(40,100,200,'red'); return {metrics:{x,f,d},controls:{x},disabled:{},title:'导数',caption:'切线斜率'}; }",
        'controls':[{'id':'x','label':'位置','min':-2.,'max':2.,'step':.1,'value':0.}],
        'covered_decision_ids':['D1'],'explanation':'原稿','limitations':['待教师审阅']}


def test_local_repair_preserves_the_entire_unrelated_math_and_controls():
    previous=program(); original=copy.deepcopy(previous)
    old="ctx.fillRect(40,100,200,'red')"
    new="ctx.fillRect(40,100,200,35)"
    result=apply_repair(previous,{'edits':[{'old':old,'new':new,'reason':'补齐高度'}],'explanation':'只修绘图参数'})
    assert result['code']==previous['code'].replace(old,new)
    assert result['controls']==previous['controls']
    assert result['covered_decision_ids']==['D1'] and result['limitations']==previous['limitations']
    assert previous==original


@pytest.mark.parametrize('anchors', [['missing'], ['x'], ['const x=p.x;', 'p.x'], ['ENTIRE'], ['ALMOST_ENTIRE']])
def test_ambiguous_missing_overlapping_and_wholesale_edits_are_rejected(anchors):
    previous=program()
    edits=[{'old':previous['code'] if a=='ENTIRE' else previous['code'][:-1] if a=='ALMOST_ENTIRE' else a,'new':'replacement','reason':'测试'} for a in anchors]
    with pytest.raises(ValueError):
        apply_repair(previous,{'edits':edits,'explanation':'测试'})


def test_invalid_anchor_gets_bounded_feedback_without_changing_original():
    previous=program(); calls=[]
    def generate(role,context,schema):
        calls.append(copy.deepcopy(context))
        assert schema is ProgramRepair
        assert context['previous_program']==previous
        old='not present' if len(calls)==1 else "ctx.fillRect(40,100,200,'red')"
        return {'edits':[{'old':old,'new':'ctx.fillRect(40,100,200,35)','reason':'正确高度'}],'explanation':'修复'}
    result=generate_program(generate,{'previous_program':previous},1)
    assert 'patch_validation_feedback' in calls[1]
    assert "const f=x*x*x-3*x; const d=3*x*x-3;" in result['code']
    assert len(calls)==2


def test_exhausted_anchor_repair_does_not_fall_back_to_wholesale_generation():
    def generate(*args):
        return {'edits':[{'old':'absent','new':'new','reason':'测试'}],'explanation':'测试'}
    with pytest.raises(AgentError,match='绑定原稿'):
        generate_program(generate,{'previous_program':program()},0)
