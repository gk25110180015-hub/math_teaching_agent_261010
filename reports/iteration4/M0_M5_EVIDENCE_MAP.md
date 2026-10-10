# M0—M5 实现与验收证据地图

## 最终更新：2026-09-24

三章自动工作流及固定产物核验全部完成：CH01 70请求/11页，CH02 152/18，CH03 191/23；三份源码ZIP实际Windows干净编译及逐页文字/链接一致，Edge分别49/68/100文件下载核验。root通读最终全部正文并打开52页图片；6组Beamer源码ZIP现均有干净编译证据。原稿固定基准为16覆盖、14覆盖/2部分、19覆盖/3部分；通用教学改进项另列，未把它们消除或计算成数学准确率。

当前版本1118本地（模型mock、含21实际Windows相关节点）与14Edge（模型mock/假传输）PASS。教师数学与逐页视觉均NOT_RUN，三章任务仍AWAITING_USER_REVIEW，自动math/policy NEEDS_REVIEW保持；M5整体仍PARTIAL / NEEDS_REVIEW。完整M0—M4入口和旧证据保留如下；最新结果、失败边界与启动/交付统一见[最终验收](FINAL_ACCEPTANCE.md)、[交付清单](DELIVERABLES.md)、[当前入口](ACTIVE_WORK.md)。

## 更新：2026-09-24 08:14 UTC

第二章最终18页已完成真实工作流和两条反馈、全源码/18页agent审读、Windows源码ZIP干净编译、Edge68文件下载；原16项14覆盖/2部分覆盖。[审读](ch02-final-audit-20260924T0316/final-audit.md)。第二、三章最终证据共同通过：[collector](final-live-evidence/20260924-031850-d5f2c6/summary.json)。第一章绝对值应用缺项仍在正式复检，超时恢复记录见[当前入口](ACTIVE_WORK.md)。

六组课件源码ZIP现均有实际干净编译记录：原有2组加本轮[补齐4组](remaining-beamer-bundles-20260924T031040-c79067/report.json)，不改历史NOT_RUN。53原件最新哈希一致：[核验](originals-recheck-20260924T080903/originals-preservation.json)。V7本地1118与Edge14的221个源文件在暂停恢复时仍匹配。M5的教师数学/视觉验收依旧NOT_RUN，不能宣布M0—M5全部验收通过。

## 更新：2026-09-24 03:08 UTC

下方原文保留为09-20历史审计；其中“当前902”“两章待完成”“240/6/6”等均仅适用于旧时间。最新部署V7为1118本地PASS、14EdgePASS，模型mock/假传输；两章持久预算480/12/12。M0—M4实现入口保持，M5仍PARTIAL/NEEDS_REVIEW：教师数学/视觉NOT_RUN，未声称完整三章矩阵全部通过。

第三章最新23页稿已完成真实工作流（191累计请求）、三条反馈均satisfied、Windows源码ZIP干净编译、Edge100文件下载和root全部23页/1190行TeX审读。原稿22项是19覆盖/3部分覆盖，不能称原稿全部覆盖。见[逐项审计](ch03-final-audit-20260923T1451/final-audit.md)、[当前交付绑定](final-live-evidence/20260923-145032-408e50/summary.json)。第二章已从134正式恢复，第一章既有批准目标缺项也已通过正式复检提交；两者新稿仍待验收。

最新分层结果、原件53/53与凭据核验、历史失败和当前恢复动作汇集于[实现测试记录](IMPLEMENTATION_AND_TESTS.md)及[恢复入口](ACTIVE_WORK.md)。原来六组Beamer522页仍是历史编译/来源/渲染证据，本次未代替教师逐页审阅。

## 历史审计正文

编制时间：2026-09-21 02:49（Asia/Shanghai；2026-09-20 18:49 UTC）。这是对已有文件的只读审计，不是一次新模型测试、编译测试或教师验收。编制时第二、三章正在第三次部署后的真实续跑中；本文不把过程快照当最终交付结论。

对照规范：[CODEX_MATH_TEACHING_AGENT_WINDOWS11.md](D:/研究生阶段/数学教学agent/CODEX_MATH_TEACHING_AGENT_WINDOWS11.md)，版本 1.0、2026-09-19，SHA-256 `02d97dfe8e50ca0766dcac5bb6602db412a855b7b96e17917df1b329036427c6`。M0—M5 位于第 1244—1280 行；T01—T60、真实三章矩阵分别见 §16.2、§16.3。原规范未修改。

**已实现可独立运行的 Windows 本机应用，M0—M4 有实际工作流与分层证据；完整 M5 仍是 PARTIAL / NEEDS_REVIEW。** 本轮最新部署的本地回归为 902 PASS，实际 Edge 为 14 PASS；模型为 mock/假传输，两者均不能替代真实章节质量、最终交付包或教师审核。教师数学和教师逐页视觉始终 **NOT_RUN**。

## 1. 证据版本与计数口径

| 轮次、时间边界 | 已执行的主要证据 | 本文采用的限制 |
|---|---|---|
| 首轮，2026-09-20 本地记录 | [首轮验收](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/FINAL_ACCEPTANCE.md)：101 本地 PASS、4 Edge PASS；三章×双模板 586 页实际渲染，但六组均因原资料缺书目而编译验收 FAIL | 当时没有启用真实 API；这是历史事实，后续接通不能倒改首轮 NOT_RUN/FAIL。早期仅检查 UI 状态的宽松 E2E 已撤回业务成功含义 |
| 第二轮，2026-09-20 05:16 前后本地快照 | [第二轮验收](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/FINAL_ACCEPTANCE.md)：546 本地 PASS；6 Edge PASS；真实 smoke/CH01 自动流程完成，CH02/03 留在 33/27 次请求的预算阻塞；六组 Beamer 编译及来源检查通过、522 页渲染 | 6 Edge 早于最后 parser/provider/math 补丁；546 对应最后 CSS 修复之前版本，后续 CSS 由真实产物只读 UI 验证。CH01 仍有计划覆盖缺口。522 是第二轮渲染记录，不是本轮全页视觉 |
| 第三轮，2026-09-20 11:35 本地完整回归 | [三模型验收](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration3/FINAL_ACCEPTANCE.md)：600 本地 PASS；原 6 Edge 加新增 5 模型选择测试；10 次真实 API 分项证据 | 3 次独立连通、6 次数学对照、1 次真实备用接口调用分开计；混合切换的首选 504 是模拟。正确对照仍有 Pro 误报；旧 CH02/03 未增额或续跑 |
| 第四轮首次合并，2026-09-20 23:32 本地完整回归 | [728 回归](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/local-full-20260920-233248-60b03228.md)、[12 Edge](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/full-e2e-deployed/20260920-152336-152ba3/result.json) | 对应反馈/归属功能部署之前；不能覆盖后来新功能 |
| 第四轮 17:34 UTC 部署 | [部署清单](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/deploy-feedback-20260920T173418-d241ec/manifest.json)、[808 回归](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/local-full-20260921-013437-ceba69a4.md)、[13 Edge](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-deployed-e2e/20260920-173448-e5238b/result.json) | 新增反馈意见、引文归属核实；尚无最终逐项反馈协议和空 SSE 响应恢复 |
| 第四轮 18:32 UTC 第三次部署，当前基线 | [七文件部署](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/deploy-feedback-receipts-20260920T183237-b6a9d6/manifest.json)、[902 回归](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/local-full-20260921-023259-069ebad8.md)、[14 Edge](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-deployed-e2e/20260920-183331-ea72a9/result.json) | 902 项用时 237.469 秒、184 文件前后 SHA 稳定、0 外网尝试；包含 21 个实际 Windows 编译相关节点，负例测试通过不等于负例编译成功。14 项 pytest 用时 193.23 秒，10 个隔离测试库人审及人审事件均 0，源码/测试/脚本不变 |

不同轮次和重叠专项不相加成独立测试总数。真实请求计数包含失败及尚无完整结果的尝试；只有有效返回才能记结构校验成功，HTTP 200 响应头本身不能记成功。有效 JSON 也不等于数学正确。未记录 token/费用不按零处理。

## 2. M0：工程、参考资料和工具链审计

**原要求：**先审已有工程、保留用户修改，核查三章和工具链，形成 repository/environment/reference/implementation 四份报告，随后进入可执行开发。

| 已实现、实际执行 | 证据 | 当前判定及范围 |
|---|---|---|
| 首次确认无已有应用工程，在独立子目录创建；后续沿用同一工程增量修改 | [工程审计](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/repository_audit.md)、[实施顺序](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/implementation_plan.md)、[M0 记录](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/M0_result.md) | 工程调查及落地已执行，没有只交付 skill/提示词 |
| Windows 11 25H2/build 26200.9457、Python 3.12.4、TeX Live 2024、绝对 XeLaTeX 路径、字体/宏包核查；项目 .venv 与锁定依赖 | [环境审计](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/environment_audit.md)、[Windows 脚本实测](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/ui_windows_validation.md) | 所列检测有证据；不是任意机器可用性的保证 |
| 三章同名讲义按 dataset/path/hash 隔离；主 TeX/PDF、FDU sty、资源及依赖清单；新完整原稿与 17 条书目来源审计 | [参考审计](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/reference_audit.md)、[新增原稿审计](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/source_audit.md) | 原 51 件加完整原稿 TeX/PDF 为 53 件；缺书目曾真实阻塞，后来经明确选项在派生副本补齐，不改原稿 |
| 本轮按既有 53 项清单只读 SHA 复核 | [2026-09-20 17:46:53 UTC 原件核对](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/originals-final-recheck/20260920-174653-befee6/originals-preservation.md) | 53/53 一致，0 更改、0 不可读；不覆盖清单外或后来新增文件，未重写原索引 |

**M0 结论：审计和原件保留有实证。** 参考文件齐全不代表数学正确或视觉合格。[style_profile](D:/研究生阶段/数学教学agent/math-teaching-agent/reference_index/style_profile.json) 是静态/历史记录，`human_checked=false`；其早期 `adaptation_compile=NOT_RUN` 不能盖过后续有产物的双模板编译，也不能反过来改写为教师通过。

## 3. M1：持久化 mock 最小闭环

**原要求：**数据模型/迁移/状态机、问题与决策、版本 plan、确认执行、独立 worker、预览与事件；一次 mock 讲义及一次 mock Beamer 完整生命周期；优先 T02/T03/T06/T11—T18/T48/T60，先解决授权删除与确认循环。

| 已接入实际应用 | 实际证据 | 判断 |
|---|---|---|
| domain/store/service/worker + loopback FastAPI/浏览器；编号 SQL 迁移、revision/hash、审批、原生 SQLite 队列和事件 | [M1](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/M1_result.md)、[M5 脚本生命周期](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/M5_result.md) | 等价原生 SQL 迁移有并发、事务和恢复测试；不是必须依赖 SQLAlchemy/Alembic |
| 问题末项自定义；精确例题/关联答案删除；新增内容位置；重复执行幂等；过期页面 409 | [首轮强化 UI 断言](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/ui_windows_validation.md)、[当前 14 Edge](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-deployed-e2e/20260920-183331-ea72a9/result.json) | 实际点击、刷新、确认、执行、下载，检查真实 TeX/ZIP；模型为 mock，不算真实教学质量验收 |
| 编译失败保留原审批；同 plan 重试不回确认；租约/fencing、取消和晚到结果拦截；浏览器关闭不取消 | [首轮 M1](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/M1_result.md)、[worker 崩溃恢复日志](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/worker_crash_recovery.log)、[902 回归](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/local-full-20260921-023259-069ebad8.md) | 含真实独立 worker 终止后重新领取，合成工作负载；不保证供应商崩溃边界恰好计费一次 |
| 本轮正式增额/重试、缓存契约失效、最新合法候选恢复；AUR 复检保留旧文件历史，当前复核只针对当前产物 | [本轮已部署实现](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/IMPLEMENTATION_AND_TESTS.md)、[预算/审批保持](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/budget-authorization-and-preservation.md)、[第三次重启表级核对](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/deploy-feedback-receipts-20260920T183237-b6a9d6/restart-preservation.json) | 24 张业务表不变；心跳表变化明确记录。局部已接受/被拒提案与全局轮数不清零 |

**M1 结论：mock 闭环、真实界面和持久恢复已执行。** T60 的确定性位置/授权/题解检查与任意自然语言教学目标的落实分开；后者仍须正文审读，不能凭 plan 字段或模型自报通过。

## 4. M2：真实讲义、数学检查、修复和编译

**原要求：**真实供应商适配、课程配置、逐节写作/局部复核/工具核算/全局依赖/TeX；至少两节且含定义、定理、例题和解答的真实小型讲义闭环；故意错误能阻塞或送审。

| 功能与实际执行 | 证据 | 结论与版本边界 |
|---|---|---|
| env-only 密钥、指定兼容接口；gpt6 默认及 Flash/Pro 可选；每次临时传输故障按优先顺序切换，保留实际模型来源 | [第三轮三模型验收](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration3/FINAL_ACCEPTANCE.md)、[配置与运行 README](D:/研究生阶段/数学教学agent/math-teaching-agent/README.md) | 三模型当时各一次真实连通 3/3；不是长期稳定性保证。数学拒绝、完整 schema 错误不靠换模型消除 |
| 严格 JSON/业务验证、有界结构修复/网络等待、持久请求预算；逐节编写、复核、局部补丁与实际编译 | [第二轮真实讲义](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/FINAL_ACCEPTANCE.md) | smoke 2/2 节、19 单元、5 页、21 次请求完成自动流程；CH01 5/5 节、63 单元、11 页、37 次。M2 小型真实闭环有实证，教师仍 NOT_RUN |
| 受限 AST/SymPy 独立子进程；错误级数/量词/定义域 fixtures；UNKNOWN 不升级，数值抽样不冒充全称证明 | [编译与数学核验](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/compiler_math_validation.md)、[数值证据分类](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/numeric_evidence_classification_validation.md)、[当前 902 节点](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/local-full-20260921-023259-069ebad8.md) | 仅覆盖提供的具体表达式与固定错误样例；第三轮一次 SymPy UNKNOWN 原因未定位，后续通过不倒称已经修复 |
| 前后节标签/实际 aux、依赖变更后旧检查失效、全章教学目标门禁、精确编译溢出→局部补丁→重审重编 | [本轮实现/专项索引](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/IMPLEMENTATION_AND_TESTS.md) | 原审批和正文保留；无 checkpoint 及多版本恢复已回归。仅可精确定位的编译问题进入补丁，其他失败不绕过 |
| 反馈逐项评估与回执：F 编号、真实引文、范围、证据单元和 repair_unit_ids 分开；每次修正后评估新正文 | [反馈协议独审](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/feedback-assessment-independent-audit.md)、[当前 14 Edge](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-deployed-e2e/20260920-183331-ea72a9/result.json) | 正式 API/SQLite/Worker/UI 已接入；只支持讲义，Beamer 非空反馈明确拒绝。显示最近一次核查快照，不代签教师；最新空反馈撤回旧显示 |
| 同 plan 预算 60/2/2→240/6/6，旧请求 33/27 及审批不清零；传输失败现场可恢复 | [首次增额](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/resume-20260920T143357-e340db/summary.json)、[预算核对](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/budget-authorization-and-preservation.md)、[空 SSE 恢复独审](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/provider-transport-recovery-independent-audit.md) | 用户已授权增额并实际执行；快照 46/37 只是 15:32 UTC 中间值，不是最终总数。CH02 请求 101 的 HTTP200 空正文是真失败，不能记成功 |

本轮固定真实对照分开保留：[审阅 v5/v6](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/REVIEW_CONTROL_COMPARISON.md) 12 次、严格预期 3/6→5/6；[引文归属](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/REVIEW_ATTRIBUTION_LIVE_CONTROLS.md) 2 次；[逐项反馈](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/FEEDBACK_CONTROL_COMPARISON.md) 4 次，其中 v2 证据协议 2/2、严格分类仍 1/2。均为针对固定问题的对照，不是课程准确率或模型权重训练；保留未符合预期的结果。

**M2 结论：真实小型闭环已达到原阶段完成条件；完整三章教学质量仍部分完成。** 本轮最终 CH02/03 是否把反馈落实到最终正文、是否再次核查新稿，必须以之后的同 job/plan/body SHA 证据判定，不能用 902/14 的 mock 结果替代。

## 5. M3：TeX 解析、来源映射与双模板

**原要求：**TeX/ZIP 输入、依赖闭包、宏注册、单元关系、来源覆盖及授权增删；默认模板与真实 FDU；复杂环境/常见宏，原稿不变，缺资源诚实阻塞。

| 已实现与实际执行 | 证据 | 验收边界 |
|---|---|---|
| 原始跨度/哈希扫描、数学环境/注释/条件隐藏、input/include/图片依赖、宏和自定义环境、题解关联；无法解释片段保留 opaque | [M3](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/M3_result.md)、[最终解析回归](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/reference_implementation_tests_final.md) | 合法 coth/setminus/leqslant/geqslant、不平衡 tabularx 等固定边界有证据，不声称理解任意 TeX |
| 实际输出独立核对来源，不只信模型 source_map；精确获批删题/题解及新增位置 | [T01—T60 索引](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/test_matrix.md)、[当前 Edge](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-deployed-e2e/20260920-183331-ea72a9/result.json) | 授权与实际 TeX 均核对，未授权遗漏/公式变化阻塞 |
| FDU 原主题复制、独立字体/导航适配、主题 hash 绑定；缺资源或歧义版本阻塞，不偷偷回退 | [M3](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/M3_result.md)、[双模板实测探针](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/layout_probe_validation.md) | 原三份 sty 哈希相同，原件未改；探针只在对应模板/引擎指纹下有效 |
| 三章真实讲义分别转换 default/FDU 六组，补齐书目的派生输入有原稿行号/hash | [第二轮双模板比较](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/beamer_comparison.md)、[完整 CH03 应用链](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/full_beamer_app-v2/report.md) | 六组编译/FID PASS，默认/FDU分别 CH01 77、CH02 76、CH03 108 页；确定性转换模型调用 0。完整 CH03 Service→Worker→交付另实测，TestClient 不称真实 TCP 浏览器 |

**M3 结论：双模板的真实材料编译与来源覆盖已有历史产物证据。** 六组依然是待教师审阅草稿；本轮未重新生成六组课件，不能把旧版本编译称当前源码所有真实材料再次验收。

## 6. M4：可测量的 Beamer 排版闭环

**原要求：**四档字号、字符预算、编译测量、语义拆分、图片约束、三态目录、overlay、全部物理页及局部修复；T32—T50 有 PDF 证据；无视觉模型时提供真实人工入口。

| 功能及实测 | 证据 | 可声明范围 |
|---|---|---|
| 短定义/举例合页，长证明按完整段落/item/环境拆分，合法字号选择，不靠截图/缩正文/删除条件消除溢出 | [M4](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/M4_result.md)、[第二轮排版修复比较](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/beamer_comparison.md) | CH03 长证明从 11→3 帧等有来源与 PDF 记录；不能安全拆的公式明确阻塞，不保证任意等式链可自动重排 |
| 一逻辑 frame 的题干/题解 pause；真实 nav 映射；全部物理页 PNG；真正中间 overlay 越界仍阻塞 | [编译/PDF 核验](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/compiler_math_validation.md)、[overlay 修正证据](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/pdf_overlay_visibility_validation.md)、[当前 Windows 节点](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/local-full-20260921-023259-069ebad8.md) | 隐藏对象必须有同 frame 另一 overlay 的对应证据才可校正，未知越界不放行；几何为启发式 |
| 三态完整一级目录、长目录合规双列/分页；真实模板区域与四档有效字号探针 | [模板探针](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/layout_probe_validation.md)、[第二轮 12/24 节目录探针](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/beamer_comparison.md) | 后者实际 24/48 共 72 页渲染及几何 PASS；任意超长标题仍需编译/复核，不能据固定探针判所有情况 |
| 预览、全部页 hash/overlay/问题、逐页人工复核和发布门禁；失败不能返回旧 PDF，新版本不覆盖被占用文件 | [交付实测](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/delivery_validation.md)、[当前 Edge](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-deployed-e2e/20260920-183331-ea72a9/result.json) | 入口已连接；自动复检旧文件列 superseded，历史下载继续可用，旧页不能代表新版本审核 |

**页数与视觉范围必须分开：**原参考 233 页的渲染仅为基线；首轮新稿 586 页带书目编译失败；第二轮改进稿 522/522 页实际渲染、来源/编译 PASS、几何 NEEDS_REVIEW。第二轮只有实现者诊断抽看，不是教师逐页验收；更不是第四轮新增模型稿的全页视觉。真实视觉模型能力未验证、未发送图片；教师逐页视觉 **NOT_RUN**。当前 Edge 截图验证的是界面行为，也不能替代上述视觉验收。

**M4 结论：约束、实测、全物理页检查和复核入口已执行；视觉合格仍待人工判断。** T36 任意等式链拆分、T41 任意超长标题、教学连贯性等保留 NEEDS_REVIEW/安全阻塞，不以没有已知裁切的特定样例外推普遍保证。

## 7. M5：Windows 集成、真实三章矩阵和最终交付

**原要求：**Windows 启停、刷新/崩溃恢复、中文路径、文件占用、额度/超时、安全；三章真实讲义、六组 Beamer 及教师记录；README 独立启动，完整源码包可干净重编译，未测有具体状态。

| 需求 | 已执行证据 | 本轮状态 |
|---|---|---|
| 用户可独立启动，不依赖 Codex 在线/WSL/Docker/Redis/Node | [README](D:/研究生阶段/数学教学agent/math-teaching-agent/README.md)、[Windows 启停实测](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/ui_windows_validation.md)、[当前部署重启核对](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/deploy-feedback-receipts-20260920T183237-b6a9d6/restart-preservation.json) | 本机实际服务与独立 worker；Setup/Run/Stop/Doctor、PS5.1/7证据为对应历史版本，不伪称本轮再次从零安装 |
| 中文/空格/括号路径、原件保护、编译进程取消、PDF 占用、ZIP/TeX 安全及受控 artifact 下载 | [Windows/数学测试](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/compiler_math_validation.md)、[交付测试](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/delivery_validation.md)、[902 Windows 节点](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/local-full-20260921-023259-069ebad8.md) | 当前相关节点实际通过；敏感值合成测试不等于当前全部交付的真实密钥扫描 |
| 实际 Edge 操作与故障恢复 | [当前 14 Edge 完整证据](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-deployed-e2e/20260920-183331-ea72a9/result.json) | PASS：真实 Edge/API/SQLite/Worker及相关 Windows 编译；mock 模型。新反馈输入、轮询不丢草稿、错误保留、成功清空、回执刷新及空意见撤回均实测；没有提交教师审核 |
| CH01 真实讲义 | [最终语义审读](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/CH01-final-semantic-comparison.md)、[11 页 agent 视觉](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/CH01-final-visual-audit.md) | 第二轮完整 11 页；批准 S02 的绝对值应用训练仍缺，教学覆盖 PARTIAL；本轮用户授权的是 CH02/03 续测，未重启 CH01 |
| CH02/CH03 真实讲义最终版本 | [CH02 从 101 正式重试](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/resume-20260920T183828-48a3fb/summary.json)、[CH03 从 122 新反馈复检](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/feedback-CH03-20260920T183829-0d222d/summary.json) | **PENDING，本文件编制时仍续跑。** 本轮早先 CH02/CH03 首次达到 AUR 的稿件仅是反馈前基线，不能当最新完成稿 |
| 六组真实 Beamer 矩阵 | [第二轮六组](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/beamer_comparison.md) | 历史编译/来源 PASS，教师 NOT_RUN；本轮未重做六组全页验收 |
| 完整源码 ZIP 在干净目录独立编译 | [第二轮交付清单](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/DELIVERABLES.md) | 真实 smoke 5 页、CH01 11 页独立重编 PASS；六包 CRC/SHA 均查，其中 CH01/default 77页及 CH03/FDU 108页另干净重编，另四包没有重编；完整 CH03 应用包另有重编。**当前 CH02/CH03 新包仍待完成后实际验收** |
| 当前产物的 UI 下载/hash、当前/历史隔离、原审批/计数链、最终真实密钥落盘扫描 | [最终验收命令](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-delivery-verification-commands.md)、[只读采集入口](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/final-evidence-collection-ready.md) | 已备好带时间戳、不覆盖历史的工具；本次文档审计**未执行**最终采集/编译/UI/密钥扫描，不把脚本存在当测试通过 |
| 教师数学、逐页视觉、正式发布 | 各轮报告及当前 14 Edge 的 10 库人审 0 | **NOT_RUN**；自动/agent 审读不构成教师签字，AWAITING_USER_REVIEW 不等于 COMPLETED |

历史 [T01—T60](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/test_matrix.md) 只能作为原覆盖索引；其中 API、预算和原件数的旧限制按本文件后续证据更新解释，原报告不倒改。T04/T60 的任意自然语言比例/难度不做通用定量正确性保证；固定题型/答案/位置可以自动核验，其余明确送审。

### trusted_local 与 T52 的准确适用边界

规范 §14.1 第 1057 行允许 `trusted_local` 用于本机、用户自己的可信资料，并要求实际输入/模板来源确认；第 1058 行规定有可用限权环境或隔离容器时使用 `isolated` 并实测限制，不可用不得称“沙箱已开启”。第 1060 行明确：

> 不要求用户为了本期功能强制安装容器，但公网、多用户、不可信上传上线前必须实现隔离模式，并禁用 trusted_local。

§14.2 第 1068 行又要求未实现权限隔离时如实披露。因此当前本机可信模式符合本期允许的边界；完整隔离未实现、T52 隔离部分 NOT_RUN 是已披露限制，不是本轮新回归，也不能把 openout 最低保护通过写成文件/网络沙箱通过。未来公网、多用户或不可信上传仍明确阻塞，M6 本期只准备迁移文档。

### CH01 未解决的批准目标证据

[CH01 S02 原审计](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/CH01-S02-semantic-recheck.json) 保存批准目标“能够处理含有有理式、绝对值和常数倍的基本数列极限”，问题 ID `CH01-S02-ABS-APPLICATION`；U12/U14 只训练常数倍、有理式、线性组合、积商，误差证明中出现绝对值不能替代绝对值极限应用训练。[最终全章报告](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/CH01-final-semantic-comparison.md) 保持 PARTIAL，绑定 revision 2、plan hash `60e76cc0b1271ac1b32a9f48c9ae760665bb7180cbdd52df6f5f5958f25db4ac`、TeX SHA `9cdf4001d836dcaf4162359c3a838f3002c14c80e6c5d00c9fa0dd599e10aaa7`。本轮没有修改 CH01 或扩大测试任务范围。

## 8. 本轮最终证据待补清单

下列项目不能用历史报告、模型空 issues 或 mock PASS 代替；本文件不预填结果：

1. CH02/CH03 无活动 job 后的正式 API/只读 DB 一致快照：原审批、输入/plan hash、33/27 原事件前缀、240/6/6 增额链、全部请求与失败/完成不确定分类、人审 0。
2. 对最新 job/plan/反馈动作的最新逐项回执，核对持久输入正文、依赖 SHA 和最终 current TeX；活动阶段的上次回执不得宣称新 patch 已复评。最新空意见必须撤回旧结果，损坏新回执不得回退旧 PASS。
3. 同一批最终 current artifact ID/SHA 的干净 Windows 源码包重编译，以及真实 Edge 只读下载/hash、旧历史下载仍可用。历史文件不参与当前复核/发布。
4. 最新 CH02/CH03 的批准目标与基准逐项比较、实际全部页/变更页 agent 视觉范围及未解决项；教师审核单独继续 NOT_RUN，未经教师实际操作不产生记录。
5. 最终当前产物与允许范围内文件的密钥落盘检查。既有第三轮扫描 37144 个文件匹配 0 的证据只对当时范围有效，不能覆盖后来新增文件。

本报告只写入自身，不修改 src/tests/scripts、生产数据库、参考索引或原件；没有重新运行通过的套件，没有调用模型，没有提交人工审核。
