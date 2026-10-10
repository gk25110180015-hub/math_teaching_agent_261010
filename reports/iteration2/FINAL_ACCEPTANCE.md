# PARTIAL / NEEDS_REVIEW — 第二轮 Windows 11 本地验收

记录日期：2026-09-20（Asia/Shanghai）。**独立应用、界面、后台工作流、真实 API、编译、检查和文件交付均已接入。第一章与两节 smoke 已完成自动流程；第二、三章仍为可恢复的预算阻塞。教师数学与逐页视觉验收 NOT_RUN，完整 M5 不标为全部通过。**

本轮使用三章参考材料和新增原稿进行比较、回归及应用改进，**没有训练或微调模型权重**。本报告取代此前进行中汇总；旧文保存在 [收尾前快照](FINAL_ACCEPTANCE-before-final-20260920-0515.md)，其它失败日志和旧产物均未覆盖。

## 可运行入口与交付

- [默认应用](http://127.0.0.1:8765)：独立新建任务；[最新启动证据](default-runtime-final.json)记录健康正常、worker存活。
- [本轮真实测试任务](http://127.0.0.1:8766)：独立工作区，可查看完整及部分产物；[启动证据](runtime-live-ui-20260920-0509.json)、[最终浏览器证据](live-ui-final-20260920-050656/README.md)。
- [交付清单](DELIVERABLES.md)：PDF、主TeX、完整源码ZIP，以及第二、三章明确标记PARTIAL的累计预览。
- [三章逐项基准对照](THREE_CHAPTER_COMPARISON.md)、[已实施改进与边界](IMPROVEMENT_COMPARISON.md)、[安装和启动](../../README.md)。

应用不依赖 Codex 会话、Node、Docker、WSL 或 Redis。服务只监听loopback。运行和测试记录保留在本地；关闭浏览器不会清除任务。

## 真实讲义结果

|案例|持久状态|已检查内容与产物|累计真实请求|自动结论|
|---|---|---|---:|---|
|两节 smoke|AWAITING_USER_REVIEW|2/2节、19单元、完整5页|21/60|content/math/compile/layout/security PASS；policy NEEDS_REVIEW|
|CH01 数列与数列极限|AWAITING_USER_REVIEW|5/5节、63单元、完整11页|37/60|content/compile/layout/security PASS；math/policy NEEDS_REVIEW|
|CH02 无穷级数|BLOCKED，S04审阅/局部修复预算|3/5节、48单元；截至S03累计10页PARTIAL|33/60|整章未完成；S04未CHECKED、S05未生成|
|CH03 函数极限与连续|BLOCKED，S03审阅/局部修复预算|2/5节、26单元；截至S02累计6页PARTIAL|27/60|整章未完成；S03未CHECKED、S04–S05未生成|

讲义累计118次实际请求，含失败和重试；每run原60次上限和驱动总240次上限保持不变。全部教师reviews为空。最终[只读运行快照](final-runtime-and-state-20260920-051655-382274-verified.md)确认两个服务/worker正常、无活动job，四run的provider.request事件计数一致，budget_actions为0。CH01/02/03持久预算60/2/2；旧smoke原始记录仅有请求上限60，其余字段UNRECORDED，UI有效值不补写为历史事实。小节CHECKED、SymPy PASS、编译PASS和页面下载成功均不等于全部数学正文正确。

CH01的16项范围内核心基准已有正确依据，独立审读未发现新的确定数学错误；但批准计划中的S02绝对值极限应用未落实，整体教学覆盖仍为PARTIAL。S04无结构化核算，不能补写math PASS。六道末尾练习答案与回链已核验；[完整语义审读](CH01-final-semantic-comparison.md)与[全部11页agent视觉检查](CH01-final-visual-audit.md)保留标题/页眉等低优先级问题，未代替教师验收。

CH02 S03的JSON故障已真实恢复，随后积分判别证明完成定向修正，但独立审读另发现U13对数级数求和下限1与文字/答案下限2矛盾，n=1未定义。两项SymPy请求只覆盖U09，不覆盖U13；这是正文覆盖与模型漏检，不能称为SymPy算错。S04 U07–U13仍有真实TeX过度转义。一般几何级数收敛范围也没有充分落实。见 [S03审读](CH02-S03-semantic-recheck.md)、[S04审计](CH02-S04-budget-audit.md)。

CH03已检查S01的单侧定义域错误已修复；S03最新审阅却漏读完整定义和已提供的S02先修证明。审阅规则v4已部署，真实正负对照改善，但**原CH03任务尚未使用v4重审**。不以新提示词或离线重放倒改旧任务通过。

CH02 U05为3次提案、1次实际接受修改；CH03 U06为3次提案、2次实际接受修改。当前每单元上限2及相关提案限制仍生效。已分别向用户提出将每单元上限2提高到3、保留总请求60及原计数的选择，尚未收到明确答复，因此没有增额或继续执行。

## 分层测试：每项只代表实际执行范围

|类型|实际结果|证据与限制|
|---|---|---|
|最终完整本地回归|**546 PASS，1 real_api deselected，0失败/跳过，223.44秒**|[报告](local-final-20260920-050545.md)、[JUnit](local-final-20260920-050545.xml)、[日志](local-final-20260920-050545.log)。110个文件前后SHA一致；live=false/key为空。包含20个实际Windows编译相关节点；6个浏览器测试未收集|
|Windows编译节点|上述546中的20项全部PASS|包含成功编译、预期失败诊断、取消及约束检查；测试PASS不表示负例编译成功，不能另加20计数|
|完整Mock浏览器工作流|**6 PASS，79.12秒**|[Edge E2E证据](ui-final-six-20260920-040716/README.md)。实际浏览器/Windows编译，模型为MOCK；此快照早于最后parser/provider/math补丁，不冒称覆盖全部最终实现|
|最后CSS修复后的真实产物UI|**四案例检查PASS，61/61文件GET与SHA一致**|[报告](live-ui-final-20260920-050656/README.md)。189个记录请求全为同源GET；smoke21、CH01 25、CH02部分9、CH03部分6个文件。真实Edge读取真实API产物，但本次验证没有模型调用或教师审核|
|JSON转义反馈专项|**77 PASS，1 real_api deselected**|[定向记录](provider_escape_feedback_validation.md)。已合入546；另有[CH02 S03真实请求20失败→21严格schema通过](CH02-S03-escape-live.md)，不能将单次恢复外推为一般成功率|
|数值抽查证据分类专项|**55 PASS**，含1项实际Windows编译|[定向记录](numeric_evidence_classification_validation.md)。实际SymPy，模型为MOCK；已合入546。成功数值抽查仅降为warning，数学总状态仍NEEDS_REVIEW，未冒充一般证明；CH02旧任务尚未真实重跑|
|已完成讲义源包干净重编译|smoke 5页、CH01 11页，均PASS|[smoke](live-zip-recompile-20260920-034007.json)、[CH01](live-zip-recompile-20260920-043108.json)。实际Windows XeLaTeX两遍，全部页文字及链接数量一致，API调用0|
|三章双模板课件|六组编译/来源PASS，522/522页渲染|[六组比较](beamer_comparison.md)。确定性转换、模型调用0；几何NEEDS_REVIEW，教师NOT_RUN|
|完整CH03课件应用链|7节、104来源单元、93逻辑帧/108物理页；124文件HTTP/SHA通过|[Service→Worker→交付](full_beamer_app-v2/report.md)。HTTP为TestClient，不能称为TCP浏览器测试；provider为MOCK，真实编译及独立源包重编译|
|教师数学及逐页视觉验收|**NOT_RUN**|agent审读、截图检查、自动几何和模型审阅不代替教师签认|

最终546回归后仅产品CSS发生改变：真实截图发现长标题挤出侧栏，增加桌面布局宽度约束后重跑四案例真实Edge检查，确认遮挡消除。110文件对比仅style.css不同，**546明确对应CSS之前快照**，CSS由之后浏览器测试验证。修复前截图和首次隐藏details造成的脚本误报均保留。

旧517、498、369等回归及早期360 PASS/1 FAIL的SQLite并发故障继续归档；不把重叠专项相加为唯一测试总数。两条锁定依赖的弃用warning保留。完整回归排除了真实API条件测试，而本表的真实API生成和下面校准均另有实际执行证据。

## API配置与审阅校准

本机Windows User环境变量已配置：MATH_AGENT_API_BASE_URL=https://oneapi.advancedsolver.com/v1，MATH_AGENT_MODEL=gpt-6-astra，live及SSE均启用。密钥仅由环境读取，不写入源码、.env、浏览器或命令参数；现有进程值优先于启动脚本导入的User值。见 [环境记录](environment_configuration.json)、[SSE实际探针](streaming_probe.json)、[能力记录](provider_streaming_capabilities.json)。

基础校准9次、课程范围校准2次、上下文v3/v4校准9次，共**20次校准请求**；另有**3次能力探针**，与讲义118次分开记录。早期带bad/good标签的初测不算独立盲测；同题复测不累加为新样本。费用未知为null，缺失token不按零处理。

上下文中性对照有2个正确与2个真实错误样例：v3为TP2/FN0/TN1/FP1；v4为TP2/FN0/TN2/FP0，两个真实错误仍阻塞。v3实际4请求，v4实际5请求（含1次schema修复）。[对照报告](review-context-comparison.md)及[部署SHA证据](reviewer_math-v4-deployment.json)记录v4在旧CH02执行结束后部署，未改运行中提示词。样本少且针对已知问题，不能外推课程准确率或视作独立模型共识。

真实文本/SSE已验证；vision、tools、服务端json_schema仍UNTESTED。客户端schema通过不等于服务端能力验证。页面图片没有交给第三方视觉模型。

## 与新增原稿的比较和实际应用改进

完整原稿8章、17书目条目已审计；三章原主TeX/PDF/主题与资源齐全。原三章51文件加新增TeX/PDF共53文件保持SHA不变，见 [全稿审计](source_audit.md)、[最终53/53原件复核](final-originals-20260920-051655-382274.json)。未覆盖原资料。

已实施并连接到实际流程的改进包括：可追溯书目补齐与显式选项、正常字号和证明拆页、UTF-8字节写入、SSE恢复、严格JSON诊断、合法AMS text数学作用域、引用锚点、独立答案与题号回链、严格局部补丁及连续证据链、数值抽查分类、上下文审阅v4、持久预算和部分稿下载、并发迁移及提示词版本证据。逐项依据、真实恢复与剩余问题见 [改进对照](IMPROVEMENT_COMPARISON.md)。

六组课件默认/FDU分别77/76/108页，共522页；原手工课件54/51/93页仅作结构参考，不当作质量分数。六份v2 ZIP逐成员CRC/SHA检查通过，其中CH01/default和CH03/FDU另在干净目录实际重编译77/108页；其余四包没有重复重编译，交付清单明确NOT_RUN。完整CH03应用交付ZIP又独立重编译108页通过。

## M0—M5状态

|阶段|已接入及运行|验收边界|
|---|---|---|
|M0|工程与三章材料审查，完整规范阅读，新增全稿与书目来源审计|原件保护通过；不宣称原稿数学完全正确|
|M1|实际UI、两输入流程、选项/自定义、计划revision/hash/diff与显式确认、SQLite任务/worker、刷新恢复|Mock E2E与真实产物只读UI分别有证据|
|M2|指定真实API/SSE、逐节生成/核算/审阅/修复、全局检查与恢复|smoke与CH01完成自动流程；CH02/03仍预算阻塞|
|M3|真实TeX/ZIP到默认/FDU课件、来源保留、精确删改及书目补齐|六组编译/来源通过；教师未审|
|M4|语义分组、合法字号、目录/overlay、全部PNG、几何报告及逐页复核入口|自动几何有复核项；教师全页视觉NOT_RUN|
|M5|Windows安装/启动/停止脚本、持久恢复、实际HTTP下载、完整ZIP及干净重编译|独立应用可用；三章真实生成及教师验收未全部完成，整体PARTIAL/NEEDS_REVIEW|

首轮[M0](../M0_result.md)、[M1](../M1_result.md)、[M2](../M2_result.md)、[M3](../M3_result.md)、[M4](../M4_result.md)、[M5](../M5_result.md)及[历史汇总](../FINAL_ACCEPTANCE.md)保持原记录；其中当时缺密钥/书目等条件没有被倒改。

## 失败、限制与后续恢复

- 失败的API、编译、补丁、测试日志、产物与预算状态均保留；旧无效JSON最早仅保存hash/错误而没有完整响应，其可恢复范围明确有限，不宣称可还原原文。
- 第二、三章继续保留BLOCKED及全部部分稿。依据[规范§5.3](D:/研究生阶段/数学教学agent/CODEX_MATH_TEACHING_AGENT_WINDOWS11.md:398)，预算耗尽后由用户选择是否增额；未收到答复不提高上限、不清零、不绕过门禁。
- CH01教学覆盖缺口、CH02正文下标/范围/TeX错误、CH03新审阅规则实际重跑均待后续处理。教师数学与逐页视觉审核始终NOT_RUN。
- trusted_local为本机原生模式，非文件系统/网络隔离；isolated尚未实现，不能据此宣称公网多用户或不可信TeX部署通过。
- 密钥检查范围：[最终文本/SQLite/WAL/SHM/环境文件精确匹配检查](secret-storage-final-20260920-0520.json)扫描33165个允许类型文件，匹配0、不可读0，PASS；[8个交付ZIP/40成员检查](delivered-zip-secret-check-20260920-0434.json)另行PASS。前者比较当前环境密钥的UTF-8/UTF-16 LE/BE字节，排除虚拟环境/git/cache及压缩文件；后者明确覆盖8个交付ZIP。未打印或保存密钥；不扩大为全盘、任意编码或历史所有密钥审计。
