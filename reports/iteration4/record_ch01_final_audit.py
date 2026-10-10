"""Record root's completed full-source and all-11-page audit, keeping teacher NOT_RUN."""
from datetime import datetime,timezone
import hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/iteration4/ch01-final-audit-20260924-final'
RID='05748ab6260c40989a560a98e1e2065a'
load=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=load(OUT/'prepared-evidence.json');render=load(OUT/'render-manifest.json')
assert sha(p['pdf']['path'])==p['pdf']['sha256']=='b65edbfe29fdbd570316ea522bbfc0dd3aed3846e4c1f80da78b2195f9b6c7e3'
assert sha(p['source']['path'])==p['source']['sha256']=='7698669ac6f26154e4ccb3cbc8b5ed851d69087fc0e6b5e281a7e262920a743f'
assert len(p['answer_relations'])==14 and len(p['pdf_links'])==6
changed=[u['unit_id'] for s in p['sections'] for u in s['changed_units']]
assert changed==['S02.U12','S02.U13']
with sqlite3.connect((ROOT/'workspace/iteration2-live/agent.db').as_uri()+'?mode=ro',uri=True) as c:
    c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
    current=dict(c.execute('SELECT * FROM runs WHERE id=?',(RID,)).fetchone())
    assert current['status']=='AWAITING_USER_REVIEW' and current['request_count']==70
    assert not c.execute("SELECT 1 FROM jobs WHERE run_id=? AND status IN ('queued','running')",(RID,)).fetchone()
    event=dict(c.execute("SELECT * FROM events WHERE run_id=? AND type='feedback.reviewed' ORDER BY sequence DESC LIMIT 1",(RID,)).fetchone())
    feedback=json.loads(event['payload_json']);assert event['sequence']==3049
    assert len(feedback['items'])==1 and feedback['items'][0]['status']=='satisfied'
    assert not c.execute('SELECT 1 FROM reviews WHERE run_id=?',(RID,)).fetchone()
criteria=[];optional=[]
for old in p['original_16_criteria']:
    if old['scope']!='REQUIRED':
        optional.append({'id':old['id'],'title':old['title'],'status':'NOT_REQUIRED'});continue
    evidence=old['evaluation']['generated_evidence']
    reason=old['evaluation']['reason']
    if old['id']=='CH01-X01':reason=reason.replace('447行之后',str(p['source']['unit_lines']['S01.U10']-1)+'行之后')
    if old['id']=='CH01-E01':reason+=' 本轮增加c_n=|3/n−2|→2；反三角不等式加ε–N定义证明绝对值极限法则，未使用函数连续性；三问均归入唯一解答S02.U13。'
    criteria.append({'id':old['id'],'title':old['title'],'status':'PASS','reason':reason,
        'method':'ROOT_REREAD_FINAL_SOURCE_AND_MATCHED_ANSWERS',
        'tex_units':[{'unit_id':e['unit_id'],'line':p['source']['unit_lines'][e['unit_id']]} for e in evidence]})
assert len(criteria)==16 and len(optional)==3
notes=[
'标题与三个定义、唯一性完整可读；标题仍含讲义计划，属编辑建议。',
'1/n例解、练习和有界/保号证明完整；页底保序定理证明续页3。',
'保序、四则和商法则证明较密但清楚；例2.7三小问题面完整，绝对值证明续页4。',
'新增绝对值定义证明与计算接续完整；练习2.8与夹逼证明完整，定理3.3证明续页5。',
'固定k证明、有界乘无穷小和振荡反例可辨；根式例3.6解答续页6。',
'根式、有理式及两道练习完整；无根号/上下标裁切。',
'单调有界及递推证明较密但无相撞；经济例题完整、解答续页8。',
'经济例解和递推练习完整；方法表在版心内，条件与结论可读，证明续页9。',
'方法说明、有理式定义法与奇偶夹逼完整，无裁切。',
'错误辨析练习和答案区清楚，蓝色题号正确；根式答案推导续页11。',
'根式/振荡答案接续、递推归纳与商法则反例完整，无缺字或公式重叠。']
assert len(render['pages'])==len(notes)==11
ledger=[]
for page,note in zip(render['pages'],notes):
    assert sha(page['png_path'])==page['png_sha256']
    ledger.append({**page,'agent_visual_review':'ACTUALLY_VIEWED_NO_CLIPPING_OR_MISSING_GLYPHS',
                   'teacher_visual_review':'NOT_RUN','observations':[note]})
common=[
 {'id':'G01','status':'PARTIAL','reason':'批准计划的逐节目标/先修链保留，PDF未逐节列简短目标/先修提示。'},
 {'id':'G02','status':'PASS','reason':'定义、条件、证明、8例及相应解答完整；方法总结重复属编辑冗余。'},
 {'id':'G03','status':'PASS','reason':'五节1/1/2/1/1道练习，8例+6练各有唯一关联答案。'},
 {'id':'G04','status':'PASS','reason':'有界不收敛、不可拆振荡因子极限、零分母极限反例及根式条件清楚。'},
 {'id':'G05','status':'PASS','reason':'实际6个PDF回链与aux编号/题面页逐个核验，未见未解析引用。'},
 {'id':'G06','status':'PASS_WITH_EDITORIAL_NOTES','reason':'实际打开11页，未见裁切/缺字；页3/7较密，多处题解跨页；教师未审。'},
 {'id':'G07','status':'PARTIAL','reason':'价格调整假设、初值、目标及数学推导正确，但货币单位、每期时间单位未注明。'},
 {'id':'G08','status':'PASS','reason':'练习答案集中页10–11，6条实际回链有效；例题答案留在正文。'}]
report={'at':datetime.now(timezone.utc).isoformat(),'mode':'ROOT_FULL_SOURCE_AND_ALL_11_IMAGES',
 'run':p['run'],'approval':p['approval'],'pdf':p['pdf'],'source':p['source'],
 'prepared_evidence_sha256':sha(OUT/'prepared-evidence.json'),'baseline_results':{'PASS':16},
 'criteria':criteria,'optional_excluded':optional,'common':common,'changed_units':changed,
 'unit_count':sum(len(s['generated']['units']) for s in p['sections']),
 'answer_relations':p['answer_relations'],'pdf_links':p['pdf_links'],'feedback_event':3049,
 'feedback_items':feedback['items'],'agent_math_review':'NO_BLOCKING_ERROR_FOUND; FIXED_BASELINE_16_COVERED; COMMON_G01_G07_PARTIAL',
 'agent_visual_review':'11/11_ACTUALLY_VIEWED_WITH_EDITORIAL_NOTES','teacher_math_review':'NOT_RUN',
 'teacher_visual_review':'NOT_RUN','model_calls_this_audit':0,
 'windows_source_zip':'PASS: ../final-source-bundles-CH01-20260924-final/report.json',
 'edge_delivery':'PASS: 49 files; ../final-delivery-ui-CH01-20260924-final/report.json',
 'binding_and_preservation':'PASS: ../ch01-final-evidence/20260924T082154-0c8003/summary.json',
 'limitations':['Agent text/visual review is not teacher acceptance or formal proof.',
 'Original 16 required criteria and 3 optional exclusions remain unchanged.',
 'Existing generic quality math/policy NEEDS_REVIEW remain, including S04 tool limits.']}
for name,data in [('final-audit.json',report),('page-review-completed.json',ledger)]:
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
lines=['# 第一章最终正文与全页审读','',
'最终11页、63单元、8例/6练、累计70次真实请求（含失败）。批准的绝对值应用已落实；原稿固定16项覆盖，3项可选扩展仍NOT_REQUIRED，未把通用教学检查的两个PARTIAL计作全部通过。教师数学/视觉验收NOT_RUN。',
'',f"本次实际通读全部{len(Path(p['source']['path']).read_text(encoding='utf-8').splitlines())}行TeX，并打开最终11张PNG。与37请求旧稿逐单元比较，仅S02.U12/U13改变；其余61单元正文不变，也重新审读。",'',
'|基准项|结果|依据与当前源码行|','|---|---|---|']
for row in criteria:lines.append('|'+row['id']+' '+row['title']+'|PASS|'+row['reason'].rstrip('。').replace('|',r'\|')+'；'+', '.join(x['unit_id']+'@'+str(x['line']) for x in row['tex_units'])+'|')
lines+=['','新增例题在第3页列三问，第3–4页唯一解答给出全部计算。|3/n−2|的内部极限−2，经反三角不等式及定义证明得绝对值极限2。实际反馈先指出正确解答误放题面，再经限定补丁归入U13；反馈3049最终satisfied。未将内容归位算作修复错误数学结论。',
'','|通用教学检查|结果|说明|','|---|---|---|']
for row in common:lines.append('|'+row['id']+'|'+row['status']+'|'+row['reason']+'|')
lines+=['','14组题解及6条PDF回链通过；新稿11页源码包在Windows干净编译，文字/链接数相同；真实Edge只读下载49个当前/历史文件通过。全部11页实际看图未见裁切/缺字/公式相撞；标题仍含讲义计划、部分页较密和题解跨页，保留编辑建议。',
'','原章参考9页，新稿仍11页；页数/字数不作为数学质量评分。价格模型货币/每期时间单位与PDF逐节目标提示仍可完善。S04归纳/确界论证不冒充SymPy形式化证明，原自动NEEDS_REVIEW保留。',
'','本次审计0模型调用。真实任务在50请求三模型超时后按原job恢复，60请求耗尽后正式增额到240；局部2/全局2不变，累计计数不清零。旧稿和失败日志保留。',
'','[逐项JSON与SHA](final-audit.json) · [逐页实际观察](page-review-completed.json)']
with (OUT/'final-audit.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
print(json.dumps({'status':'RECORDED','baseline':report['baseline_results'],'pages':11,'changed_units':changed,'units':report['unit_count']},ensure_ascii=False))
