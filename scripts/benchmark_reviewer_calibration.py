"""Opt-in real-model reviews of three authored error/control fixtures, with durable results."""
import argparse
import json
from pathlib import Path
from math_agent.domain import MathReview
from math_agent.pipeline import Pipeline
from math_agent.provider import CompatibleChatProvider, PROMPTS
from math_agent.settings import Settings, PROJECT_ROOT
from math_agent.util import AgentError, now, scrub, write_json, digest

CASES={
 'CH01':{
  'topic':'数列极限的定义与性质',
  'bad':r'称实数列 $a_n$ 收敛于 $A$，如果存在一个 $\varepsilon>0$，使得存在正整数 $N$，对所有 $n>N$ 都有 $|a_n-A|<\varepsilon$。这就是通常的数列极限定义。',
  'good':r'设 $a_n$ 为实数列，$A\in\mathbb R$。若对任意 $\varepsilon>0$，存在正整数 $N$，使所有正整数 $n>N$ 都满足 $|a_n-A|<\varepsilon$，则称 $a_n$ 收敛于 $A$。',
  'expected_error':'epsilon存在量词不能替代任意量词；条件只能约束最终落在某固定邻域，不能定义趋近。'},
 'CH02':{
  'topic':'级数收敛的必要条件与交错级数',
  'bad':r'因为 $1/n\to0$，所以正项级数 $\sum_{n=1}^{\infty}1/n$ 收敛。通项趋于零足以保证级数收敛。',
  'good':r'交错调和级数 $\sum_{n=1}^{\infty}(-1)^{n-1}/n$ 条件收敛：其正项大小 $1/n$ 单调递减并趋于零，故由交错级数判别法收敛；其绝对值级数是已知发散的调和级数，因此不是绝对收敛。',
  'expected_error':'通项趋零仅为必要条件；调和级数发散。'},
 'CH03':{
  'topic':'函数极限与连续的区别',
  'bad':r'令 $f(x)=x^2$（当 $x\ne0$），$f(0)=1$。由于 $\lim_{x\to0}f(x)=0$ 存在，所以 $f$ 在 $0$ 处连续；无需核对该极限是否等于 $f(0)$。',
  'good':r'若函数 $g$ 在 $x_0$ 的某邻域有定义，且 $\lim_{x\to x_0}g(x)=g(x_0)$，则称 $g$ 在 $x_0$ 处连续。极限存在与函数在该点连续是不同的要求。',
  'expected_error':'连续还要求极限等于点值；本例0不等于1，在0不连续。'},
}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-live',action='store_true')
    parser.add_argument('--neutral-ids',action='store_true',help='Use neutral IDs and alternate the order of error/control units')
    parser.add_argument('--run-dir',type=Path,help='Fresh evidence directory under this project reports directory')
    args=parser.parse_args()
    root=(args.run_dir or PROJECT_ROOT/'reports/iteration2'/('reviewer-calibration-neutral' if args.neutral_ids else 'reviewer-calibration')).resolve()
    if not root.is_relative_to((PROJECT_ROOT/'reports').resolve()):
        parser.error('--run-dir must stay inside this project reports directory')
    root.mkdir(parents=True,exist_ok=True)
    state_path=root/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'created_at':now(),'request_count':0,'request_limit':12,'records':[],'cases':{}}
    def save():write_json(state_path,state)
    def before(metadata):
        if state['request_count']>=state['request_limit']:raise AgentError('BUDGET_EXHAUSTED','Calibration budget exhausted')
        state['request_count']+=1
        state['records'].append({'type':'request','timestamp':now(),**metadata});save()
    def record(metadata):
        state['records'].append({'type':'result','timestamp':now(),**metadata});save()
    settings=Settings()
    identity={'reviewer_prompt_hash':digest((PROMPTS/'reviewer_math.md').read_bytes()),
              'schema_hash':digest(MathReview.model_json_schema()),'fixtures_hash':digest(CASES),
              'pipeline_hash':digest(Path(__import__('math_agent.pipeline',fromlist=['']).__file__).read_bytes()),
              'model':settings.model,'base_url':settings.api_base_url,'neutral_ids':args.neutral_ids}
    if not args.execute_live:
        print('NOT_RUN: use --execute-live; requires environment credential.')
        return 0
    if state.get('request_count') and state.get('identity')!=identity:
        raise AgentError('CALIBRATION_IDENTITY_CHANGED','保留旧校准结果；提示/协议已变更，请使用新的 --run-dir')
    state['identity']=identity;save()
    provider=CompatibleChatProvider(settings,before_request=before,record=record,failure_dir=root/'provider-failures')
    p=object.__new__(Pipeline);p.settings=settings;p.provider=provider
    for name,fixture in CASES.items():
        if state['cases'].get(name,{}).get('execution')=='PASS':continue
        path=root/name;path.mkdir(exist_ok=True)
        order=['good','bad'] if args.neutral_ids and name!='CH02' else ['bad','good']
        identifiers={kind:name+('.U0'+str(i+1) if args.neutral_ids else '.'+kind) for i,kind in enumerate(order)}
        units=[{'id':identifiers[kind],'kind':'explanation','tex':fixture[kind]} for kind in order]
        write_json(path/'fixture.json',{**fixture,'units':units,'expected_blocking_ids':[identifiers['bad']],'expected_no_math_issue_ids':[identifiers['good']]})
        try:
            review=p.review_units(units,{'scope':{'kind':'section_local','current_section':{'title':fixture['topic']},'pending_sections':[]},
                'plan':{'topic':fixture['topic'],'prerequisites':['实数、绝对值、基本量词；本节陈述引用的已知判别法可用。']},
                'instruction':'逐单元检查数学陈述，不要求当前独立练习夹具提供整章、例题或每个引用定理的完整证明；不得假定所有陈述正确。'},path,'actual')
            flagged={i['unit_id'] for i in review['issues'] if i['severity'] in ('blocking','review')}
            blocking={i['unit_id'] for i in review['issues'] if i['severity']=='blocking'}
            result={'execution':'PASS','model':settings.model,'review':review,'true_positive':int(identifiers['bad'] in flagged),'false_negative':int(identifiers['bad'] not in flagged),
                'true_negative':int(identifiers['good'] not in flagged),'false_positive':int(identifiers['good'] in flagged),
                'known_error_classified_blocking':identifiers['bad'] in blocking,'teacher_review':'NOT_RUN'}
        except Exception as exc:
            result={'execution':'FAIL','error_type':type(exc).__name__,'message':scrub(str(exc)),'teacher_review':'NOT_RUN'}
        write_json(path/('result-'+now().replace(':','').replace('.','')+'.json'),result)
        state['cases'][name]=result;save()
    totals={k:sum(c.get(k,0) for c in state['cases'].values()) for k in ('true_positive','false_negative','true_negative','false_positive')}
    report={'status':'PASS' if len(state['cases'])==3 and all(c['execution']=='PASS' and c['known_error_classified_blocking'] and not c['false_positive'] for c in state['cases'].values()) else 'NEEDS_REVIEW',
      'kind':'REAL_API_AUTHORED_FIXTURES','neutral_ids':args.neutral_ids,'request_count':state['request_count'],'totals':totals,
      'teacher_review':'NOT_RUN','limitations':['六个已知、基础、人工编写的校准单元，不是随机盲测或完整教学正确率；未调整模型权重。','比较基准是明确的数学定义与反例；不以措辞相似度评分。']}
    write_json(root/'summary.json',report)
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report['status']=='PASS' else 2

if __name__=='__main__':raise SystemExit(main())
