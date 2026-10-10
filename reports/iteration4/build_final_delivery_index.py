"""Create a final index only after all three frozen audits and actual delivery checks exist."""
from datetime import datetime,timezone
import hashlib,json,sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/iteration4'
WS=ROOT/'workspace/iteration2-live'
load=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
link=lambda title,p:f'[{title}](<{Path(p).as_posix()}>)'
paths={
 'CH01':('05748ab6260c40989a560a98e1e2065a','ch01-final-audit-20260924-final','final-source-bundles-CH01-20260924-final','final-delivery-ui-CH01-20260924-final'),
 'CH02':('fd6736af6ef14be3839e019e86ca1e5c','ch02-final-audit-20260924T0316','final-source-bundles-CH02-20260924T0316','final-delivery-ui-CH02-20260924T0317'),
 'CH03':('a45be503af594ce8aae0bb1e4c30184b','ch03-final-audit-20260923T1451','final-source-bundles-CH03-20260923T1451','final-delivery-ui-CH03-20260923T1452')}
assert not (OUT/'DELIVERABLES.md').exists() and not (OUT/'FINAL_ACCEPTANCE.md').exists()
collector23=load(OUT/'final-live-evidence/20260924-031850-d5f2c6/summary.json')
assert collector23['status']=='PASS' and collector23['final_delivery_snapshot_ready']
collector1_path=sorted((OUT/'ch01-final-evidence').glob('*/summary.json'))[-1]
collector1=load(collector1_path);assert collector1['status']=='PASS'
secret_path=sorted(OUT.glob('final-secret-delta-*.json'))[-1]
secret=load(secret_path);assert secret['status']=='PASS' and len(secret['archives'])==9
original_path=OUT/'originals-recheck-20260924T080903/originals-preservation.json'
assert load(original_path)['counts']=={'PASS':53}
cases=[]
with sqlite3.connect((WS/'agent.db').as_uri()+'?mode=ro',uri=True) as c:
    c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
    for case,(rid,audit_dir,bundle_dir,ui_dir) in paths.items():
        run=dict(c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone())
        assert run['status']=='AWAITING_USER_REVIEW'
        assert not c.execute("SELECT 1 FROM jobs WHERE run_id=? AND status IN ('queued','running')",(rid,)).fetchone()
        assert not c.execute('SELECT 1 FROM reviews WHERE run_id=?',(rid,)).fetchone()
        audit=load(OUT/audit_dir/'final-audit.json')
        bundle=load(OUT/bundle_dir/'report.json');ui=load(OUT/ui_dir/'report.json')
        assert bundle['status']==ui['status']=='PASS'
        compiled=bundle['cases'][0]
        artifacts={}
        for name in ['lecture.pdf','lecture.tex','source_bundle.zip','quality_report.json']:
            row=dict(c.execute("SELECT * FROM artifacts WHERE run_id=? AND name=? AND status!='superseded' ORDER BY created_at DESC,rowid DESC LIMIT 1",(rid,name)).fetchone())
            path=WS/row['storage_key'];assert sha(path)==row['sha256']
            artifacts[name]={'path':str(path),'sha256':row['sha256'],'artifact_id':row['artifact_id']}
        assert artifacts['lecture.pdf']['sha256']==compiled['original_pdf_sha256']
        assert artifacts['source_bundle.zip']['sha256']==compiled['zip_sha256']
        assert artifacts['lecture.pdf']['sha256']==(audit['pdf_sha256'] if case=='CH03' else audit['pdf']['sha256'])
        ledger=load(OUT/audit_dir/'page-review-completed.json')
        assert len(ledger)==compiled['page_count']
        assert all((row.get('agent_visual_review') or row.get('agent_visual_status','')).startswith(('ACTUALLY_VIEWED','VIEWED')) for row in ledger)
        assert audit['teacher_math_review']==audit['teacher_visual_review']=='NOT_RUN'
        summary=collector1['request_summary'] if case=='CH01' else collector23['cases'][case]['request_summary']
        assert summary['totals']['attempts']==run['request_count']
        cases.append({'case':case,'run_id':rid,'status':run['status'],'request_count':run['request_count'],
           'pages':compiled['page_count'],'artifacts':artifacts,'baseline':audit['baseline_results'],
           'request_summary':summary,'audit':str(OUT/audit_dir/'final-audit.md'),
           'source_zip_verification':str(OUT/bundle_dir/'report.json'),'edge_verification':str(OUT/ui_dir/'report.json'),
           'automatic_quality':{key:load(artifacts['quality_report.json']['path'])[key]['status'] for key in ('content','math','compile','layout','policy','security')},
           'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'})
beamer=load(ROOT/'workspace/iteration2-delivery/delivery-20260920-020236.json')
additional_path=OUT/'remaining-beamer-bundles-20260924T031040-c79067/report.json'
additional=load(additional_path);assert additional['status']=='PASS'
extra={x['case']:x for x in additional['cases']}
for case in beamer['cases']:
    assert sha(case['pdf'])==case['pdf_sha256'] and sha(case['bundle'])==case['bundle_sha256']
    assert case['clean_recompile']=='PASS' or extra[case['case']]['status']=='PASS'
manifest={'at':datetime.now(timezone.utc).isoformat(),'status':'REVIEWABLE_DELIVERY_TEACHER_NOT_RUN',
 'cases':cases,'beamer_cases':beamer['cases'],'extra_beamer_recompile':str(additional_path),
 'secret_storage':str(secret_path),'originals':str(original_path),'ch01_binding':str(collector1_path),
 'ch02_ch03_binding':str(OUT/'final-live-evidence/20260924-031850-d5f2c6/summary.json'),
 'model_calls_this_index':0,'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'}
lines=['# 最终交付清单','',
'独立Windows本地应用已实现，当前三章讲义完成自动工作流与交付核验，均待教师审核。以下链接绑定当前实际文件SHA；旧稿、失败日志和检查点均保留。',
'',link('启动与环境说明',ROOT/'README.md')+' · '+link('分层验收报告',OUT/'FINAL_ACCEPTANCE.md'),
'','应用入口：[新建任务](http://127.0.0.1:8765)；[三章基准任务](http://127.0.0.1:8766)。如服务未运行，按README启动相应工作区。',
'','## 真实API生成讲义','','|章|页数／累计请求|PDF|TeX|完整源码ZIP|检查与对照|','|---|---|---|---|---|---|']
for row in cases:
    a=row['artifacts']
    lines.append('|'+row['case']+'|'+str(row['pages'])+' / '+str(row['request_count'])+'|'+link('PDF',a['lecture.pdf']['path'])+'|'+link('TeX',a['lecture.tex']['path'])+'|'+link('ZIP',a['source_bundle.zip']['path'])+'|'+link('原稿对照/审读',row['audit'])+' · '+link('自动检查',a['quality_report.json']['path'])+'|')
lines+=['','## 原资料转双模板课件','','这六组为真实本机解析、排版和编译产物，不计为模型生成测试。共522个物理页的历史渲染保留；全部六个ZIP已有干净目录编译证据（此前2组、本轮补4组）。教师逐页验收未执行。',
'','|数据/模板|页数|PDF|TeX|源码ZIP|','|---|---|---|---|---|']
for row in beamer['cases']:lines.append('|'+row['case']+'|'+str(row['physical_pages'])+'|'+link('PDF',row['pdf'])+'|'+link('TeX',row['main_tex'])+'|'+link('ZIP',row['bundle'])+'|')
lines+=['','原生XeLaTeX采用trusted_local模式，不是文件系统/网络隔离沙箱。所有讲义的数学/策略检查仍保留NEEDS_REVIEW，agent审读不代替教师签认。',
'',link('文件SHA、请求与验收绑定',OUT/'delivery-manifest.json')]
(OUT/'DELIVERABLES.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
lines=['# 最终开发与验收记录','',
'独立应用、三模型路由、持久任务、局部修复、反馈回执、Windows编译、页面预览及文件交付已接入并实际测试。M0—M4有实现和执行证据；M5自动化与三章产物核验完成，教师数学/视觉验收未执行，整体仍是PARTIAL / NEEDS_REVIEW，不宣布全部验收通过。',
'',link('交付文件',OUT/'DELIVERABLES.md')+' · '+link('M0—M5证据地图',OUT/'M0_M5_EVIDENCE_MAP.md'),
'','## 分层测试','','|层次|已执行结果|边界|','|---|---|---|',
'|完整本地回归|1118 PASS，0失败/错误/跳过，1 live排除|模型mock/假传输，含21个实际Windows相关节点；负例测试通过不代表负例编译成功|',
'|完整Edge工作流|14 PASS|真实Edge/API/SQLite/worker，模型mock/假传输，无教师签认|',
'|三章真实API|三章均到AWAITING_USER_REVIEW|累计请求含失败和恢复，结构合法不等于数学正确|',
'|最终讲义源码ZIP|3/3 Windows新目录编译，逐页文字与链接数一致|实际XeLaTeX；不是视觉验收|',
'|当前与历史下载|三章真实Edge只读下载核验PASS|绑定同批artifact ID和SHA，无模型调用|',
'|Agent完整审读|三章源码通读、全部最终页实际看图|原稿差异和排版建议保留；不是教师验收|',
'|双模板课件|6/6编译、来源检查及源码ZIP重编有实证|522页历史渲染；本轮补4个ZIP重编，其余2个引用原证据|',
'|教师数学/逐页视觉|NOT_RUN|未调用/reviews，未把自动质量报告改成教师通过|',
'','本地与Edge版本：'+link('1118项报告',OUT/'local-full-20260923-230959-0068cbb3.md')+'、'+link('14项Edge',OUT/'final-deployed-e2e/20260923-150959-2c67a2/result.json')+'。未改变生产源码后不重复运行全套，后续reports工具变化有独立证据。',
'','## 三组参考对照与改进','','|章|页数／累计请求|原稿固定基准|正文落实|','|---|---|---|---|']
improvements={'CH01':'补绝对值极限实际例题，反三角不等式与定义证明，唯一关联解答完整；旧题保留。',
'CH02':'补极限比较实际计算比值3，修正全章答案导航；几何级数/望远镜求和仍部分覆盖。',
'CH03':'补独立夹逼练习、加减抵消反例、经济单位；修复正弦界及指数差商前提链；3项原稿范围仍部分覆盖。'}
for row in cases:lines.append('|'+row['case']+'|'+str(row['pages'])+' / '+str(row['request_count'])+'|'+str(row['baseline'].get('PASS',0))+'覆盖 / '+str(row['baseline'].get('PARTIAL_BASELINE',0))+'部分覆盖|'+improvements[row['case']]+' '+link('逐项依据',row['audit'])+'|')
lines+=['','参考资料用于评估、检索与工作流改进，没有训练模型权重，也没有未见课程的泛化验证。模型曾误报原本正确的部分和证明和有限项边界；它们不计为数学错误修复。固定审阅对照严格预期从3/6到5/6，仍有严重度差异；反馈协议新版结构2/2有效，严格分类1/2。见'+link('质量与对照记录',OUT/'QUALITY_COMPARISON.md')+'。',
'','## API稳定性与恢复','','|任务|尝试|结构校验成功|记录失败|完成不确定|','|---|---|---|---|---|']
for row in cases:
    m=row['request_summary']['totals']
    lines.append('|'+row['case']+'|'+str(m['attempts'])+'|'+str(m['validated_successes'])+'|'+str(m['recorded_failures'])+'|'+str(m['completion_uncertain'])+'|')
lines+=['','默认gpt6，临时传输故障按gpt6→deepseek-flash→deepseek-v4-pro切换；数学否决、完整结构错误和明确拒绝不靠换模型抹除。确实发生504、超时和HTTP200后无有效正文；CH01一次三个供应商全部不可用，保留检查点后正式恢复。API不能保证始终有可用模型；超时可能已计费，usage不完整，不按零费用处理。新增SSE顶层error分支有mock专项证据，未声称该分支真实线上命中。',
'','每次正式增额/复检/重试保留原计划、审批、累计计数和旧事件。CH02/03为480请求/每单元12/全局12；CH01请求240、局部2/全局2。未重置预算，也未丢弃失败草稿。',
'','## 原件、配置与限制','',
'53件清单内原件SHA全部一致：'+link('原件核验',original_path)+'。密钥仅由环境变量读取；先前220574个选定文本/DB文件扫描0匹配，本轮增量扫描与9个最终ZIP成员核对见'+link('最新记录',secret_path)+'。不把限定扫描范围称作任意编码的全盘证明。',
'','稿件仍有标题/证明重复、部分分页和留白等编辑建议；三章自动数学/策略NEEDS_REVIEW保持。原生trusted_local编译未实现完全隔离。早期Windows子进程0xC0000005根因未确定，随后独立与多次完整回归未复现，不声称已修复；其他失败及候选误用真实环境记录见'+link('完整实施记录',OUT/'IMPLEMENTATION_AND_TESTS.md')+'。',
'',link('三章文件与证据绑定',OUT/'delivery-manifest.json')]
(OUT/'FINAL_ACCEPTANCE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
(OUT/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':manifest['status'],'chapters':len(cases),'lecture_pages':sum(c['pages'] for c in cases),
                  'requests':sum(c['request_count'] for c in cases),'delivery':str(OUT/'DELIVERABLES.md')},ensure_ascii=False))
