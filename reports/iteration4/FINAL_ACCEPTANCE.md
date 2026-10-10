# 最终开发与验收记录

独立应用、三模型路由、持久任务、局部修复、反馈回执、Windows编译、页面预览及文件交付已接入并实际测试。M0—M4有实现和执行证据；M5自动化与三章产物核验完成，教师数学/视觉验收未执行，整体仍是PARTIAL / NEEDS_REVIEW，不宣布全部验收通过。

[交付文件](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/DELIVERABLES.md>) · [M0—M5证据地图](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/M0_M5_EVIDENCE_MAP.md>)

## 分层测试

|层次|已执行结果|边界|
|---|---|---|
|完整本地回归|1118 PASS，0失败/错误/跳过，1 live排除|模型mock/假传输，含21个实际Windows相关节点；负例测试通过不代表负例编译成功|
|完整Edge工作流|14 PASS|真实Edge/API/SQLite/worker，模型mock/假传输，无教师签认|
|三章真实API|三章均到AWAITING_USER_REVIEW|累计请求含失败和恢复，结构合法不等于数学正确|
|最终讲义源码ZIP|3/3 Windows新目录编译，逐页文字与链接数一致|实际XeLaTeX；不是视觉验收|
|当前与历史下载|三章真实Edge只读下载核验PASS|绑定同批artifact ID和SHA，无模型调用|
|Agent完整审读|三章源码通读、全部最终页实际看图|原稿差异和排版建议保留；不是教师验收|
|双模板课件|6/6编译、来源检查及源码ZIP重编有实证|522页历史渲染；本轮补4个ZIP重编，其余2个引用原证据|
|教师数学/逐页视觉|NOT_RUN|未调用/reviews，未把自动质量报告改成教师通过|

本地与Edge版本：[1118项报告](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/local-full-20260923-230959-0068cbb3.md>)、[14项Edge](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-deployed-e2e/20260923-150959-2c67a2/result.json>)。未改变生产源码后不重复运行全套，后续reports工具变化有独立证据。

## 三组参考对照与改进

|章|页数／累计请求|原稿固定基准|正文落实|
|---|---|---|---|
|CH01|11 / 70|16覆盖 / 0部分覆盖|补绝对值极限实际例题，反三角不等式与定义证明，唯一关联解答完整；旧题保留。 [逐项依据](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/ch01-final-audit-20260924-final/final-audit.md>)|
|CH02|18 / 152|14覆盖 / 2部分覆盖|补极限比较实际计算比值3，修正全章答案导航；几何级数/望远镜求和仍部分覆盖。 [逐项依据](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/ch02-final-audit-20260924T0316/final-audit.md>)|
|CH03|23 / 191|19覆盖 / 3部分覆盖|补独立夹逼练习、加减抵消反例、经济单位；修复正弦界及指数差商前提链；3项原稿范围仍部分覆盖。 [逐项依据](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/ch03-final-audit-20260923T1451/final-audit.md>)|

参考资料用于评估、检索与工作流改进，没有训练模型权重，也没有未见课程的泛化验证。模型曾误报原本正确的部分和证明和有限项边界；它们不计为数学错误修复。固定审阅对照严格预期从3/6到5/6，仍有严重度差异；反馈协议新版结构2/2有效，严格分类1/2。见[质量与对照记录](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/QUALITY_COMPARISON.md>)。

## API稳定性与恢复

|任务|尝试|结构校验成功|记录失败|完成不确定|
|---|---|---|---|---|
|CH01|70|64|6|0|
|CH02|152|119|30|3|
|CH03|191|148|43|0|

默认gpt6，临时传输故障按gpt6→deepseek-flash→deepseek-v4-pro切换；数学否决、完整结构错误和明确拒绝不靠换模型抹除。确实发生504、超时和HTTP200后无有效正文；CH01一次三个供应商全部不可用，保留检查点后正式恢复。API不能保证始终有可用模型；超时可能已计费，usage不完整，不按零费用处理。新增SSE顶层error分支有mock专项证据，未声称该分支真实线上命中。

每次正式增额/复检/重试保留原计划、审批、累计计数和旧事件。CH02/03为480请求/每单元12/全局12；CH01请求240、局部2/全局2。未重置预算，也未丢弃失败草稿。

## 原件、配置与限制

53件清单内原件SHA全部一致：[原件核验](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/originals-recheck-20260924T080903/originals-preservation.json>)。密钥仅由环境变量读取；先前220574个选定文本/DB文件扫描0匹配，本轮增量扫描与9个最终ZIP成员核对见[最新记录](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-secret-delta-20260924T082153-8769f2.json>)。不把限定扫描范围称作任意编码的全盘证明。

稿件仍有标题/证明重复、部分分页和留白等编辑建议；三章自动数学/策略NEEDS_REVIEW保持。原生trusted_local编译未实现完全隔离。早期Windows子进程0xC0000005根因未确定，随后独立与多次完整回归未复现，不声称已修复；其他失败及候选误用真实环境记录见[完整实施记录](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/IMPLEMENTATION_AND_TESTS.md>)。

[三章文件与证据绑定](<D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/delivery-manifest.json>)
