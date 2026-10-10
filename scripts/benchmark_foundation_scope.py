"""Real API regression: declared real-number foundations versus an explicit tool exclusion."""
import argparse
import copy
import json
from pathlib import Path

from math_agent.domain import MathReview
from math_agent.provider import CompatibleChatProvider, PROMPTS
from math_agent.settings import PROJECT_ROOT, Settings
from math_agent.util import AgentError, digest, now, scrub, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-live',action='store_true')
    args=parser.parse_args()
    if not args.execute_live:
        print('NOT_RUN: requires --execute-live and environment configuration.')
        return 0
    root=PROJECT_ROOT/'reports/iteration2/foundation-scope-calibration'
    if root.exists():
        raise SystemExit('Evidence directory already exists; preserve it and use a separately named follow-up script/run.')
    root.mkdir(parents=True)
    original=PROJECT_ROOT/'workspace/iteration2-live/b/05748ab6260c4098/sS04_275ca369f149/repair-1.json'
    section=json.loads(original.read_bytes())['section']
    by_id={u['id']:u for u in section['units']}
    units=[{**copy.deepcopy(by_id['S04.U03']),'id':'U01'},
           {**copy.deepcopy(by_id['S04.U04']),'id':'U02','relates_to':'U01'}]
    cases=[
        {'id':'C01','excluded':['本题教学方案明确禁止引用上确界、下确界及等价的完备性性质。单调有界定理在本题只作为已知结论使用，不证明它。'],
         'expect_proof_issue':True},
        {'id':'C02','excluded':['不引入超出本科一年级微积分范围的实数完备性公理体系'],
         'expect_proof_issue':False}]
    settings=Settings()
    state={'created_at':now(),'request_count':0,'request_limit':6,'records':[],'cases':[],
           'model':settings.model,'prompt_hash':digest((PROMPTS/'reviewer_math.md').read_bytes()),
           'source_sha256':digest(original.read_bytes()),'teacher_visual_review':'NOT_RUN'}
    def save():write_json(root/'state.json',state)
    def before(metadata):
        if state['request_count']>=state['request_limit']:
            raise AgentError('BUDGET_EXHAUSTED','Scope calibration bounded request budget exhausted')
        state['request_count']+=1;state['records'].append({'type':'request',**metadata});save()
    def record(metadata):
        state['records'].append({'type':'result',**metadata});save()
    provider=CompatibleChatProvider(settings,before_request=before,record=record,failure_dir=root/'provider-failures')
    for case in cases:
        context={'plan':{'difficulty':'本科一年级微积分','exclusions':case['excluded'],
                         'lecture':{'proof_policy':'key'}},
                 'units':units,'actual_unit_ids':['U01','U02'],
                 'scope':{'kind':'section_local','current_section':{'title':'单调有界原理'},'pending_sections':[]},
                 'instruction':'仅审所提供定理与证明及明确课程限制，不要求提供整章。核查数学正确性和是否使用被明确排除的工具；不要臆造教师审批。'}
        folder=root/case['id'];folder.mkdir()
        write_json(folder/'model-input.json',context)
        write_json(folder/'local-expectation-not-sent.json',case)
        try:
            review=provider.generate('reviewer_math',context,MathReview)
            write_json(folder/'response.json',review)
            coverage=set(review['checked_unit_ids'])=={'U01','U02'}
            valid_ids=all(i['unit_id'] in {'U01','U02'} for i in review['issues'])
            flagged=any(i['unit_id']=='U02' and i['severity'] in ('blocking','review') for i in review['issues'])
            unwanted=any(i['severity'] in ('blocking','review') for i in review['issues']) if not case['expect_proof_issue'] else False
            result={'case':case['id'],'status':'PASS' if coverage and valid_ids and flagged==case['expect_proof_issue'] and not unwanted else 'FAIL',
                    'coverage_complete':coverage,'proof_flagged':flagged,'expected_flagged':case['expect_proof_issue'],
                    'review':review,'teacher_visual_review':'NOT_RUN'}
        except Exception as error:
            result={'case':case['id'],'status':'FAIL','error_type':type(error).__name__,'message':scrub(str(error))}
        state['cases'].append(result);save()
    summary={'status':'PASS' if all(c['status']=='PASS' for c in state['cases']) else 'NEEDS_REVIEW',
             'request_count':state['request_count'],'cases':state['cases'],'prompt_hash':state['prompt_hash'],
             'teacher_visual_review':'NOT_RUN','limitations':[
                 'Two authored scope scenarios on the same mathematically valid proof, not independent mathematical accuracy samples.',
                 'Prompt regression only; no approval change, original run mutation, TeX compilation or teacher review.']}
    write_json(root/'summary.json',summary)
    print(json.dumps({'status':summary['status'],'requests':summary['request_count'],'report':str(root/'summary.json')},ensure_ascii=True))
    return 0 if summary['status']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())
