"""Record root's completed full-source/23-image review; independently verify bindings/links."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import pdfplumber
from pdfminer.pdftypes import resolve1

ROOT=Path(__file__).resolve().parents[2]
REPORTS=ROOT/'reports/iteration4'
OUT=REPORTS/'ch03-final-audit-20260923T1451'
WS=ROOT/'workspace/iteration2-live'
RID='a45be503af594ce8aae0bb1e4c30184b'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
canonical=lambda obj:json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def save(name,data):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)

freeze=json.loads((OUT/'freeze-render-manifest.json').read_bytes())
pdf_path=Path(freeze['inputs']['pdf']['path'])
tex_path=Path(freeze['inputs']['tex']['path'])
tex=tex_path.read_text(encoding='utf-8')
assert sha(pdf_path.read_bytes())=='c3c0d06df0b58fa54fc0891318e382a9dd35b0d329b5a368d20fcb8e0ddf8991'
assert sha(tex_path.read_bytes())=='ee0d1bdbc780f997d2e9beb7be6598d82f8860d87dc15a821c1311d1a077082b'
sections=[]
with sqlite3.connect((WS/'agent.db').as_uri()+'?mode=ro',uri=True) as c:
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
    run=dict(c.execute('SELECT * FROM runs WHERE id=?',(RID,)).fetchone())
    assert run['status']=='AWAITING_USER_REVIEW' and run['request_count']==191
    assert not c.execute("SELECT 1 FROM jobs WHERE run_id=? AND status IN ('running','queued')",(RID,)).fetchone()
    approval=dict(c.execute('SELECT * FROM approvals WHERE run_id=? AND revision=2',(RID,)).fetchone())
    assert approval['hash']=='fbd172c8df0c12fca976e9067b04afe5210016559e210ca8dd0c3e7d37f3f1f7'
    for sid in ['S01','S02','S03','S04','S05']:
        row=c.execute('SELECT * FROM steps WHERE run_id=? AND step_key=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(RID,'section.'+sid)).fetchone()
        data=json.loads(row['output_json']);assert sha(canonical(data))==row['output_hash']
        state_path=WS/'runs'/RID/'local-repair'/(sid+'.json')
        state=json.loads(state_path.read_bytes());raw=(WS/state['candidate_key']).read_bytes()
        assert state['phase']=='CHECKED' and sha(raw)==state['candidate_hash']
        assert json.loads(raw)==data['generated'] and not state['pending_issues']
        assert sha((WS/data['source_key']).read_bytes())==data['source_hash']
        for dep in state.get('evidence_dependencies',[]):assert sha((WS/dep['key']).read_bytes())==dep['hash']
        for u in data['generated']['units']:assert u['tex'] in tex,u['id']
        sections.append({'section_id':sid,'generated':data['generated'],'checkpoint_sha256':row['output_hash'],
                         'local_state_sha256':sha(state_path.read_bytes()),'candidate_sha256':sha(raw)})
    event=c.execute("SELECT * FROM events WHERE run_id=? AND type='feedback.reviewed' ORDER BY sequence DESC LIMIT 1",(RID,)).fetchone()
    feedback=json.loads(event['payload_json']);assert event['sequence']==2635
    assert len(feedback['items'])==3 and all(i['status']=='satisfied' for i in feedback['items'])

links=[];relations=[]
aux=pdf_path.with_suffix('.aux').read_text(encoding='utf-8')
with pdfplumber.open(pdf_path) as pdf:
    assert len(pdf.pages)==23
    page_ids={p.page_obj.pageid:p.page_number for p in pdf.pages}
    for section in sections:
        for q in section['generated']['units']:
            if q['kind'] not in ('exercise','example'):continue
            answers=[u for u in section['generated']['units'] if u['kind']=='solution' and u.get('relates_to')==q['id']]
            assert len(answers)==1
            relations.append({'question':q['id'],'kind':q['kind'],'answer':answers[0]['id']})
            if q['kind']!='exercise':continue
            label='mathagent:exercise:'+sha(canonical([section['section_id'],q['id']]))
            line=next(l for l in aux.splitlines() if l.startswith(r'\newlabel{'+label+'}'))
            number,aux_page,_,anchor=re.search(r'\{\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}',line).groups()
            dest=resolve1(pdf.doc.get_dest(anchor.encode('ascii')))
            if isinstance(dest,dict):dest=resolve1(dest['D'])
            target=page_ids[dest[0].objid];assert target==int(aux_page)
            occurrences=[p.page_number for p in pdf.pages for a in p.annots
                         if resolve1(a['data'].get('A',{})).get('D')==anchor.encode('ascii')]
            assert len(occurrences)==1
            links.append({'question':q['id'],'answer':answers[0]['id'],'number':number,
                          'question_page':target,'answer_page':occurrences[0],'anchor':anchor,'status':'PASS'})
assert len(relations)==17 and len(links)==7

# Actual root view_image calls covered each image, pages 1 through 23, on 2026-09-23.
observations=[
'标题及点/单侧/无穷远定义清楚，页底定理完整；标题仍含“讲义计划”，属编辑建议。',
'唯一性三角不等式、分段函数及左右极限清楚，无裁切。',
'练习1.8完整；运算法则、复合前提及局部有界证明可读。',
'乘积和倒数误差界完整；复合证明结束，夹逼示范在下页继续。',
'夹逼示范接续正确；保号两种符号及约分条件清楚。',
'独立夹逼练习2.7及分母清楚；无穷大正负量词可读。',
'高低同阶、o记号及两基本极限完整；证明开头接下页。',
'三角不等式与有限二项式、求和上下标均可辨。',
'上确界、子列、根式误差及有理幂界完整，公式不越界。',
'实数参数推广、负侧反号正确显示；替换定理跨页续读。',
'商替换前提及乘积证明分式清晰，无相撞。',
'反例原式极限1与错误替换0对照完整，练习3.6未缺。',
'点连续、闭区间端点与间断类型清楚，单侧定义接续。',
'单侧无穷极限和分类说明完整；文字较密但无缺字。',
'连续四则与复合证明清楚；复合定理重复陈述，属编辑冗余。',
'重复复合证明及两道连续性示例完整，分段条件清楚。',
'练习4.8与闭区间先修说明清楚；最大值证明自然接下页。',
'最大值证明接续、三个条件反例及二分证明完整。',
'介值证明与代数最值例清晰；经济题面有元/千克及一周单位。',
'经济解与三道练习完整；页底答案引言后下页又有答案标题，导航重复但无内容丢失。',
'答案1.8、2.7与新增夹逼答案全部可读；蓝色题号可回链。',
'答案4.8、5.8、5.9及经济题解可读；表格在页内，说明接下页。',
'表格单位说明及三个零点区间接续完整；末页留白较多，无裁切或缺漏。']
ledger=json.loads((OUT/'page-review-ledger.json').read_bytes())
for row,note in zip(ledger,observations):
    assert sha((OUT/row['image_path']).read_bytes())==row['image_sha256']
    row.update(agent_visual_status='VIEWED_NO_CLIPPING_OR_MISSING_GLYPHS',observations=[note],teacher_visual_status='NOT_RUN')
save('page-review-completed.json',ledger)

# Explicit assessments, preserving all 22 original criteria and the 3 optional exclusions.
assessments={
'D01':('S01.U01',[1],'PASS','去心邻域有定义确保可趋近；量词顺序正确，点值不决定极限。'),
'D02':('S01.U02 S01.U03',[1],'PASS','左右与正负无穷远的方向分别定义。'),
'T01':('S01.U04 S01.U05',[1,2],'PASS','双侧等价两侧同一有限值，取共同δ证明两方向。'),
'P01':('S01.U07 S01.U09',[2],'PASS','ε/3三角反证和δ=ε/3验证均正确。'),
'D03':('S03.U01 S04.U03',[6,13,14],'PARTIAL_BASELINE','正负无穷与绝对无穷、无穷小定义正确；未单列原稿非零无穷小与倒数无穷大的等价关系，属于基准覆盖差异。'),
'T02':('S02.U02 S02.U03 S02.U06 S02.U07',[3,4,5],'PASS','局部界M、分母远离零及正负保号证明有效。'),
'T03':('S02.U02 S02.U03 S02.U04 S02.U05 S02.U12 S02.U13',[3,4,5,6,21],'PASS','复合最终不取目标点条件明确；夹逼示范及独立练习同域同趋近，两端趋0。'),
'P02':('S02.U08 S02.U09',[5],'PASS','只在x≠1处约分并用定义求2，不把原函数补定义。'),
'T04':('S03.U03 S03.U04',[7,8,9,10],'PARTIAL_BASELINE','sin x/x与指数差商有非循环证明，Euler数列定义已给；原稿连续(1+x)^(1/x)及参数推广未系统给出。批准目标为常用基本极限，不要求擅自扩写。'),
'P03':('S03.U04',[7,8,9,10],'PARTIAL_BASELINE','三角几何界、Euler单调有界和上确界、固定有理幂误差、实幂保序、两侧差商链正确；没有原稿取整夹逼推广。实幂保序延拓和上确界作为明确基础使用。'),
'D04':('S03.U02',[7],'PASS','同一趋近、非零比较分母、高阶0、同阶有限非零常数与等价1一致。'),
'T05':('S03.U05 S03.U06 S03.U07 S03.U08',[10,11,12],'PASS','乘积/商前提正确；(x+x²)~x但相减再除x²给1和0，明确抵消风险。'),
'E01':('S03.U07 S03.U08 S03.U09 S03.U10',[12,21,22],'PASS','乘积例及指数差商练习均得1，保留定义域条件；不要求照搬log例。'),
'D05':('S04.U01 S04.U02',[13],'PASS','点值与极限相等；闭区间端点只取相应单侧。'),
'T06':('S04.U04 S04.U05 S04.U06 S04.U07',[14,15,16],'PASS','分母非零、复合域兼容及η/δ衔接正确，重复陈述属编辑问题。'),
'D06':('S04.U03 S04.U08 S04.U09 S04.U10 S04.U11 S04.U12 S04.U13',[13,14,16,17,22],'PASS','明确本讲义分类约定，补值4、跳跃左右1与2及无穷量词均正确。'),
'T07':('S05.U01 S05.U02 S05.U03 S05.U04 S05.U05 S05.U06',[17,18],'PASS','有限闭区间及连续条件、取得最值区别于有界，退化区间单独处理。'),
'T08':('S05.U07 S05.U08 S05.U09 S05.U10',[18,19],'PASS','异号内点存在与端点零值区分，介值含端点且不声称唯一。'),
'P04':('S05.U01 S05.U04 S05.U08 S05.U10',[17,18,19],'PASS','明确上确界和区间套基础；有界反证、倒数取最大及二分零点证明无循环。'),
'E02':('S04.U12 S04.U13 S05.U17 S05.U21',[17,20,22],'PASS','补值a=4；三次函数端点异号，差式因子严格正给唯一。'),
'A01':('S05.U13 S05.U14 S05.U18 S05.U22',[19,20,22,23],'PASS','价格元/千克、同周数量千克一致；20/3及32/3正确；连续性给存在，严格单调给唯一，非负折线多根反例有效。'),
'X01':('S01.U12 S02.U12 S03.U09 S04.U12 S05.U16 S05.U17 S05.U18',[3,6,12,17,20,21,22,23],'PASS','5节均有例练；10例+7练各有唯一解答，新增小问完整，7个实际PDF回链逐个核对。')}
baseline=json.loads((REPORTS/'ch03-audit-preparation-20260920T154547210089Z/audit-preparation.json').read_bytes())
unit_map={u['unit_id']:u for u in json.loads((OUT/'tex-unit-map.json').read_bytes())}
criteria=[]
for item in baseline['required_checklist']:
    units,pages,status,reason=assessments[item['id'].removeprefix('CH03-')]
    criteria.append({'id':item['id'],'title':item['title'],'status':status,'reason':reason,'pdf_physical_pages':pages,
        'tex_units':[{'unit_id':uid,'line':unit_map[uid]['start_line']} for uid in units.split()]})
common_notes=[
'计划目标/先修及5节顺序已核对；PDF未逐节重印目标，基础几何、实数完备性及实幂均说明。',
'定义、证明、例题、练习和末尾答案构成完整链；冗余不计作新知识覆盖。',
'5节各有例与练，17题解关联与7条实际PDF回链核验通过。',
'保号零值、约分域、加减抵消及最值条件反例均有具体解释。',
'已看全部编号/引用显示，无??；回链目的页与aux逐个一致。',
'23/23页实际打开，未见裁切/缺字/公式重叠；标题及部分证明重复、末页疏，保留编辑建议。',
'两经济题均为明确简化教学假设，有单位/时间尺度及存在与唯一边界。',
'例解邻近，练习答案集中页21–23；页20多余答案引言略重复，7回链实际有效。']
common=[{'id':g['id'],'check':g['check'],'status':'PASS_WITH_EDITORIAL_NOTES' if i in (0,5,7) else 'PASS','reason':common_notes[i]} for i,g in enumerate(baseline['common_checklist'])]
report={'at':datetime.now(timezone.utc).isoformat(),'mode':'ROOT_AGENT_FULL_SOURCE_AND_ALL_PAGES_AUDIT',
    'run_id':RID,'request_count':191,'approval':approval,'pdf':str(pdf_path),'pdf_sha256':sha(pdf_path.read_bytes()),
    'tex':str(tex_path),'tex_sha256':sha(tex_path.read_bytes()),'page_count':23,
    'baseline_results':dict(Counter(c['status'] for c in criteria)),'criteria':criteria,'common':common,
    'optional_excluded':[{'id':i['id'],'title':i['title'],'status':'NOT_REQUIRED'} for i in baseline['optional_excluded_checklist']],
    'feedback_event':2635,'feedback_items':[{'id':i['id'],'status':i['status'],'reason':i['reason']} for i in feedback['items']],
    'sections':sections,'answer_relations':relations,'pdf_links':links,
    'agent_math_review':'NO_BLOCKING_ERROR_FOUND_WITHIN_APPROVED_SCOPE; 3 ORIGINAL_BASELINE_PARTIAL',
    'agent_visual_review':'23/23 ACTUALLY_VIEWED; NO_CLIPPING_OR_MISSING_GLYPHS_OBSERVED; EDITORIAL_NOTES',
    'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN','model_calls_this_audit':0,
    'clean_windows_compile':'PASS; ../final-source-bundles-CH03-20260923T1451/report.json',
    'edge_delivery':'PASS; ../final-delivery-ui-CH03-20260923T1452/report.json',
    'preservation_and_final_feedback_binding':'PASS; ../final-live-evidence/20260923-145032-408e50/summary.json',
    'limitations':['Agent audit is not formal verification or teacher acceptance.','Reference items are fixed; partial original-scope items are not silently removed from the denominator.','Historical invalid responses and unresolved statement text remain in evidence; final disposition is bound to this actual body.']}
save('final-audit.json',report)
lines=['# 第三章最终正文与全页审读','',
'最终固定稿为23页，原任务累计191请求。批准范围内未发现需要阻断交付的数学错误；原稿22项为19项覆盖、3项部分覆盖，教师数学/视觉验收未执行。',
'',f'三条反馈经实际修改及新稿回执均为 satisfied；本审计重新阅读全部{len(tex.splitlines())}行TeX并打开23页PNG，未以回执代替核查。',
'','|基准项|结果|证据与判断|','|---|---|---|']
for r in criteria:lines.append('|'+r['id']+' '+r['title']+'|'+r['status']+'|'+r['reason']+' PDF页'+','.join(map(str,r['pdf_physical_pages']))+'；'+', '.join(u['unit_id']+'@TeX:'+str(u['line']) for u in r['tex_units'])+'|')
lines+=['','全部17题解关联和7个实际PDF回链通过。独立夹逼新题 x²/(2+cos(1/x)) 用x²/3与x²夹逼得0；抵消原式为1、错误替换为0；经济模型的价格/数量/共同一周与数值结果一致。',
'','指数证明由Euler数列单调有界、上确界、固定有理幂极限及实幂保序建立不等式，再处理正负差商。没有把导数、Taylor或待证极限当前提；基础实幂构造本身作为已说明先修，并非本讲义完整重建实数系统。',
'','编辑建议：标题仍含“讲义计划”；夹逼定义/定理与复合连续证明重复；指数证明较长；页20答案引言与页21标题重复，页23较疏。没有删正文来压页，没有把上述冗余计作数学错误。',
'','测试分开：真实模型任务191累计请求（含失败）；本审计模型调用0；源码ZIP在新目录实际Windows编译PASS，23页文字/链接数量相同；真实Edge下载100个当前/历史文件PASS；agent全23页实际看图完成；教师数学/视觉NOT_RUN。',
'','[逐项JSON及文件SHA](final-audit.json) · [逐页实际观察](page-review-completed.json)']
with (OUT/'final-audit.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
print(json.dumps({'status':'RECORDED','baseline':report['baseline_results'],'pages':len(ledger),'relations':len(relations),'links':len(links)},ensure_ascii=False))
