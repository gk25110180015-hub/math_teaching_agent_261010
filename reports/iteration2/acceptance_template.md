# 第二轮验收汇总草稿

记录日期：2026-09-20（Asia/Shanghai）。此文汇总已有证据并保留待完成字段，**不是最终全部通过声明**。真实讲义流程和第二轮完整回归仍在进行；单次文本连通、MOCK、实际 Windows 编译和教师审核分别认定。

## 待收尾字段

| 字段 | 当前值 | 完成后应填写 |
|---|---|---|
| `live_end_to_end` | IN_PROGRESS；已有真实响应与失败恢复证据，尚未认定完整通过 | smoke、CH01、CH02、CH03 各 run ID、最终状态、真实调用数/usage、编译与检查产物 |
| `full_regression` | PENDING；第二轮尚无统一最终回归结论 | 精确命令、日志/JUnit、通过/失败/跳过数量及未测条件；不得累加重叠专项数量 |
| `final_runtime_restart` | PENDING；由主任务重启最终 8765 服务 | 重启日志、首页/API 健康、worker 存活、配置摘要（不得含密钥） |
| `teacher_math_review` | NOT_RUN | 独立教师对数学、先修、证明、难度与选择落实的审核记录 |
| `teacher_visual_review` | NOT_RUN | 每份最终 PDF 全部物理页/overlay 的人工审核与对应哈希 |
| `final_acceptance` | PENDING / NEEDS_REVIEW | 待以上结果完成后形成结论，不能用本草稿代替 |

主任务正在修复并恢复真实 smoke。已落盘的 [运行摘要](live-lectures/summary.json) 和 [持久状态](live-lectures/benchmark_state.json) 可能仍显示上一尝试 BLOCKED；这属于保留的真实失败记录，不应重写成 PASS，也不能据旧快照推断正在运行进程的最新阶段。正式 CH01/CH02/CH03 须等 smoke 门禁满足后再开始。

## 已有第二轮证据

| 类别 | 已执行的结果与边界 | 证据 |
|---|---|---|
| Windows User 环境配置 | 用户授权后隐藏输入，key_configured=true；报告不含密钥；配置本身不算 API 测试 | [environment_configuration.json](environment_configuration.json)、[配置脚本](../../scripts/Configure-LiveApi.py) |
| 真实 API 最小文本检查 | 指定接口/model 返回 `OK`；只证明文本连通，当时 vision/tools/schema/streaming 能力未测 | [provider_initial_check.log](provider_initial_check.log) |
| 真实 SSE 文本探针 | HTTP200、4块、完整终止、回复OK；流式文本能力PASS；长非流式曾约60秒504，完整流式讲义待重试 | [streaming_probe.json](streaming_probe.json) |
| 全稿审计与原件保护 | 8 章全稿、17 个真实书目；三章数学正文一致/只有末尾排版差异；原 51 文件哈希仍一致 | [审计](source_audit.md)、[JSON](source_audit.json) |
| 三章 × 默认/FDU | 6 组真实 Windows 编译和来源核验 PASS；77/76/108 页各两份，共522物理页全部渲染；几何无 blocking，仍 NEEDS_REVIEW | [比较报告](beamer_comparison.md)、[机器记录](beamer_comparison.json)、[第一轮对照快照](beamer_comparison_before.json) |
| 12/24 节目录容量 | 实际 FDU 编译、24+48页全渲染；标题保留，来源/编译/自动几何 PASS；人工未验收 | [directory_capacity.json](directory_capacity.json) |
| 实际浏览器与书目补齐 | 原4例通过；新增第5例初次末尾换行断言失败，修测试后定向通过；计划可见、刷新、原件保护、真实 PDF/ZIP/全部 PNG；provider 全部 MOCK | [UI 报告](ui_validation.md)、[首轮日志](ui-20260920-013742-499.log)、[定向复测](ui-20260920-013940-823-bibliography.log)、[书目核验](ui-e2e/20260920-013941/bibliography-verification.json) |
| 独立工作区脚本参数 | PS5.1 中25条模拟断言PASS；修复中文UTF8进程记录读取；未启动真实应用/未碰默认8765 | [说明与局限](ui_workspace_script_validation.md)、[JSON](ui_workspace_script_checks.json) |
| 原稿/书目专项 | 全稿专项11通过；上传书目整合6通过；两者是专项结果，不加总为完整回归 | [全稿日志](manuscript_tests_final.log)、[整合日志](bibliography_integration_after.log) |
| 基准驱动离线测试 | 13通过；含假 Worker 的本地编排测试、预算与不可覆盖失败档案；不等于真实 API 或编译 | [说明](benchmark_driver_validation.md)、[日志](benchmark_offline_tests.log) |
| 真实首节片段修复 | 离线16通过；真实已保存候选的 Windows 编译1通过，无新 API 请求；尚非完整讲义 | [诊断与证据](live_content_diagnosis.md)、[离线日志](lecture_fragments_unit.log)、[Windows日志](lecture_fragments_windows.log) |
| 核算协议 | 7项实际 SymPy 子进程检查；明确区分符号、数值抽查及缺条件未检查；不等于模型已正确请求和使用 | [calculation_protocol_checks.md](calculation_protocol_checks.md) |
| 审阅/依赖/内部 actor 专项 | 修复与定向结果分别留档；benchmark_driver 只自动审批基准计划，不能冒充教师 review | [actor](actor_after.log)、[局部审阅](review_scope_after.log)、[先修依赖](plan_dependencies_after.log)、[标签引用](reference_labels_after.log) |

小 TeX 的完整原稿补书目选项默认 false；UI 显式勾选后才启用。原始 upload、原快照及全稿未改写；独立派生副本和 `plan.source_enrichment` 保存条目原文/出处/哈希，并进入计划确认。测试已核对刷新及下载 `plan.json` 的来源记录一致。原稿中有条目不等于出版信息已联网核实。

## 真实讲义当前范围

真实基准按两节数列极限 smoke → CH01 数列与数列极限 → CH02 无穷级数 → CH03 函数极限与连续执行。固定选择、范围和预算见 [驱动说明](benchmark_driver_validation.md)。内部 actor 使用 `benchmark_driver`，不会调用教师逐页 review/publish。

最初真实计划曾因先修依赖门禁失败，后续真实候选暴露重复环境、局部审阅范围和核算协议问题；有限供应商重试也曾耗尽。相关 `live_smoke_first.log`、`live_smoke_retry1.log`、`live_smoke_retry2.log` 及 [smoke 尝试档案](live-lectures/smoke/attempts/) 原样保留。修复后的完整重试结果待补；不能用本地片段编译成功推定 smoke 或三章真实生成已经通过。

原讲义基准的只读预检没有发送 API 请求：[预检摘要](benchmark-preflight/summary.json)。原讲义9/10/16页及原手工课件54/51/93页是不同基线；新生成文本不按字面相同评价，页数/密度改善也不自动代表数学或教学质量提高。

## 第一轮基线（历史证据，未覆盖）

| 范围 | 历史结果 | 路径 |
|---|---|---|
| 首轮总验收与 M0—M5 | 保留当时缺环境密钥、缺书目及未人工审核的结论；其中前两项已在第二轮获得新条件 | [FINAL_ACCEPTANCE.md](../FINAL_ACCEPTANCE.md) |
| 本地逻辑/mock/状态/安全/Windows集成 | 101 passed、5 deselected；是首轮结果，不称为第二轮全量回归 | [日志](../final-local-tests-v3.log)、[JUnit](../final-local-tests-v3.xml) |
| Windows Setup、启动→停止→恢复 | 实际锁定安装、中文/空格/括号路径、状态恢复通过 | [UI/脚本报告](../ui_windows_validation.md)、[Setup](../windows_setup_smoke_retest.log)、[恢复记录](../windows_script_smoke.json) |
| 编译、核算、打包与交付 | 实际 XeLaTeX、取消、占用PDF新版本、干净目录ZIP重编译等；具体未测项见报告 | [编译数学](../compiler_math_validation.md)、[交付](../delivery_validation.md)、[布局探针](../layout_probe_validation.md) |
| 第一轮三章双模板 | 来源PASS、586页全渲染，但缺书目导致编译验收FAIL；保留对照，未追改历史结论 | [reference_matrix.md](../reference_matrix.md)、[JSON](../reference_matrix.json) |
| 第一轮浏览器 | 4例强化通过；更早过宽断言被明确纠正 | [强化报告](../ui_windows_validation.md)、[纠正记录](../e2e/ACCEPTANCE_NOTES.md) |

所有失败继续保留日志、原始响应/候选、编译产物、plan/approval 与可恢复状态。真实请求费用未知时不编造；供应商响应边界崩溃可能重复计费。当前原生 `trusted_local` 不等于文件系统/网络隔离，教师审核、真实模型视觉与公网多用户部署不能由上述自动测试认定通过。
