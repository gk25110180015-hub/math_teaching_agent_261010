"""Record root's actual full-source and 18-page review of the frozen CH02 final draft."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/iteration4/ch02-final-audit-20260924T0316'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
prepared=json.loads((OUT/'prepared-evidence.json').read_bytes())
render=json.loads((OUT/'render-manifest.json').read_bytes())
assert sha(prepared['pdf']['path'])==prepared['pdf']['sha256']=='32e94d81b39373fde2bc33ffa50e7d6492f0c627c3ea50ddff1e00cea8729bca'
assert sha(prepared['source']['path'])==prepared['source']['sha256']=='f17e7672f38ebc61f589cb2205c1caccb238700d545438c8bdfc220525b47393'
assert len(prepared['answer_relations'])==18 and len(prepared['pdf_links'])==10
assert len(render['pages'])==18
reasons={
'D01':'通项、有限部分和与部分和数列有限极限区分正确；定义和定理重复属于编辑冗余。',
'T01':'PARTIAL: 只系统讨论a>0、r≥0的几何级数，r=0单列、负公比明确排除；批准正项范围内正确，未覆盖原稿完整实公比范围。',
'P01':'PARTIAL: 2^-n部分和1−2^-n完整；1/[n(n+1)]练习仅求前三项和3/4与判断依据，答案满足题面，但没有原稿一般望远镜求和推导。',
'T02':'n≥2时a_n=S_n−S_(n−1)推出必要条件；调和级数给出逆命题反例。',
'T03':'两个收敛级数的线性运算、有限初项差及固定n后令m趋无穷的余项正确；收敛加发散的反证展开有效。',
'P02':'有限二进分组得到H_(2^m)≥1+m/2，不依赖未证明的无穷重排。',
'T04':'明确正项在本讲义包含零，非负项部分和单调与有界准则对应。',
'T05':'比较大小和收敛/发散方向正确，最终成立的情形通过有限初项处理；实际例练条件齐全。',
'T06':'p≤0用通项不趋零，0<p≤1用有限分组，p>1用有限积分上界；覆盖所有实p。',
'T07':'正连续递减和从2开始的log例合法；积分上界/单调及整数到实数夹逼闭合。新增(3n+1)n²/(n³+2)→3实际使用极限比较；原直接4/n²比较仍正确。',
'D02':'绝对收敛与收敛但非绝对收敛的两个条件区分清楚。',
'T08':'0≤a_n+|a_n|≤2|a_n|，再相减两个已知收敛级数，无循环论证；有限三角不等式后取极限合法。',
'T09':'b_n≥0、从首项单调、趋零给出收敛及≤下一项的余项界；符号为下一项同号或零。',
'P03':'偶部分和单调有界、奇部分和差趋零；初值m=1单列，后续m≥2，未使用未定义S0。',
'E01':'分类及每道答案正确；999、8、10、4分别是所给充分误差界要求的整数截断，不声称实际误差的最小截断；条件收敛加绝对收敛和抵消反例有效。',
'X01':'8例+10练各有唯一解答；全章答案导航已修正，10个实际PDF回链与题号/目的页逐个验证。'}
pages={'D01':[1,2],'T01':[7,8],'P01':[2,15],'T02':[2,3],'T03':[3,4,5],
'P02':[3],'T04':[5,6],'T05':[6,8,9,16],'T06':[7,8],'T07':[6,8,9],
'D02':[10,12,13],'T08':[12,13],'T09':[10,11,12],'P03':[10,11,12],
'E01':[11,13,14,16,17,18],'X01':[15,16,17,18]}
criteria=[]
for old in prepared['original_16_criteria']:
    short=old['id'].removeprefix('CH02-')
    criteria.append({'id':old['id'],'title':old['title'],
        'status':'PARTIAL_BASELINE' if short in ('T01','P01') else 'PASS',
        'reason':reasons[short],'pdf_physical_pages':pages[short],
        'tex_units':[{'unit_id':x['unit_id'],'line':prepared['source']['unit_lines'][x['unit_id']]} for x in old['evidence']]})
observations=[
'标题、定义与收敛定理完整，定义/定理重复但无缺字。',
'部分和例解、练习与必要条件清楚，公式均在版心内。',
'有限分组、线性及反证说明可读，无裁切。',
'有限项改变与余项说明清楚；页底例2.7解答续下页，属于可优化分页。',
'前页例解接续完整；非负约定与定理3.3完整，证明续页6。',
'比较和极限比较条件/证明完整，分式与下标清楚。',
'几何和p级数分类清晰；公式无相撞。',
'p级数、积分判别证明与例解较密，仍可辨认，无越界。',
'极限比较新增计算清楚；页底交错定义跨页续读。',
'交错定义接续、奇偶证明和余项界清楚；例4.4续页11。',
'例解、余项证明和练习较密但无缺字；重复余项证明属编辑冗余。',
'余项证明接续、绝对/条件收敛定义完整。',
'绝对收敛证明和例解较密，公式可辨。',
'综合判别例练清楚；练习5.9题干位于页底，小问续页15。',
'练习5.9接续和全章答案导航完整；导航较长，答案在本页开始。',
'练习答案顺序与蓝色题号可读；末题接页17。',
'比较与交错答案完整，999被明确称作充分上界要求；练习5.9有限尾和公式完整，极限续页18。',
'尾和界接续正确，n=4含义明确；三个条件收敛判断和反例完整，末页有留白。']
ledger=[]
for page,note in zip(render['pages'],observations):
    assert sha(page['png_path'])==page['png_sha256']
    ledger.append({**page,'agent_visual_review':'ACTUALLY_VIEWED_NO_CLIPPING_OR_MISSING_GLYPHS',
        'observations':[note],'teacher_visual_review':'NOT_RUN'})
report={'at':datetime.now(timezone.utc).isoformat(),'mode':'ROOT_FULL_SOURCE_AND_ALL_18_IMAGES',
    'run':prepared['run'],'approval':prepared['approval'],'pdf':prepared['pdf'],'source':prepared['source'],
    'prepared_evidence_sha256':sha(OUT/'prepared-evidence.json'),
    'baseline_results':dict(Counter(x['status'] for x in criteria)),'criteria':criteria,
    'answer_relations':prepared['answer_relations'],'pdf_links':prepared['pdf_links'],
    'changed_units_since_61_requests':['S02.U10','S02.U14','S03.U12','S03.U14','S04.U03','S05.U18'],
    'feedback':{'F1':'SATISFIED: actual full-chapter navigation','F2':'SATISFIED: actual limit-comparison example',
        'final_event_sequence':2789,'bound_evidence':'../final-live-evidence/20260924-031850-d5f2c6/summary.json'},
    'review_calibration':'S02.U10 and U14 were already mathematically valid; added detail is not counted as correction of a mathematical error. Prior direct comparison remains valid; added limit comparison fills the teaching goal. No arbitrary new verdict used.',
    'agent_math_review':'NO_BLOCKING_ERROR_FOUND_IN_APPROVED_SCOPE; TWO_ORIGINAL_BASELINE_PARTIAL',
    'agent_visual_review':'18/18_ACTUALLY_VIEWED_WITH_EDITORIAL_NOTES',
    'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN','model_calls_this_audit':0,
    'windows_source_zip':'PASS: ../final-source-bundles-CH02-20260924T0316/report.json',
    'edge_delivery':'PASS: 68 files; ../final-delivery-ui-CH02-20260924T0317/report.json'}
for name,data in [('final-audit.json',report),('page-review-completed.json',ledger)]:
    with (OUT/name).open('x',encoding='utf-8') as stream:json.dump(data,stream,ensure_ascii=False,indent=2)
lines=['# 第二章最终正文与全页审读','','固定18页、累计152请求。批准范围内未发现阻断数学错误；原稿16项对照14项覆盖、2项部分覆盖，未缩小分母。教师数学/视觉验收均未执行。',
    '',f"实际通读全部{len(Path(prepared['source']['path']).read_text(encoding='utf-8').splitlines())}行TeX并打开18张页面PNG。题解关联18组（8例、10练）及10个实际PDF返回链接核验通过。",'',
    '|基准项|结果|判断|','|---|---|---|']
for item in criteria:lines.append('|'+item['id']+' '+item['title']+'|'+item['status']+'|'+item['reason'].replace('|',r'\|')+'；'+', '.join(x['unit_id']+'@TeX:'+str(x['line']) for x in item['tex_units'])+'|')
lines+=['','两条反馈实际完成：极限比较例中比值趋于3，答案导航明确指向全章答案区；最新2789回执均satisfied，固定正文与回执的绑定由collector再次验证。',
    '','保留编辑建议：定义/定理重复、余项证明重复，几处题面/证明分页和较长答案导航。公式未见越界、裁切或缺字。S02的两个补充不算修复原数学错误，旧直接比较也仍正确。',
    '','测试分别记录：真实任务累计152请求（包含失败）；本次审读0模型调用；Windows干净ZIP重编译18页及文字/链接核验通过；真实Edge下载68个当前/历史文件通过；agent18页实际看图完成；教师NOT_RUN。',
    '','[逐项证据与SHA](final-audit.json) · [逐页实际观察](page-review-completed.json)']
with (OUT/'final-audit.md').open('x',encoding='utf-8') as stream:stream.write('\n'.join(lines)+'\n')
print(json.dumps({'status':'RECORDED','baseline':report['baseline_results'],'pages':len(ledger)},ensure_ascii=False))
