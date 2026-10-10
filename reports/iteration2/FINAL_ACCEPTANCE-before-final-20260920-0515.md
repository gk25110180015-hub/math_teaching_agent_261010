# IN_PROGRESS — 第二轮 Windows 11 本地验收汇总

记录日期：2026-09-20（Asia/Shanghai）。**独立应用已实现并运行；两节真实 API smoke 已完成自动检查并停在待人工复核；正式三章真实生成仍在进行，完整 M5 验收尚未完成。** 本文是主任务收尾前的事实汇总，保留 IN_PROGRESS，不能读成所有项目 PASS。

## 当前交付与待完成项

| 项目 | 当前结论 |
|---|---|
| 独立默认应用 | `http://127.0.0.1:8765`，新代码已重启，健康 `ok`、worker 存活，真实 API 与流式开关已启用；见 [runtime-after-budget-20260920.json](runtime-after-budget-20260920.json) |
| 真实 API 两节 smoke | 2/2节、5页，`AWAITING_USER_REVIEW`；content/math/compile/layout/security PASS，policy NEEDS_REVIEW；没有教师审核 |
| CH01 数列与数列极限，完整真实生成 | **AWAITING_USER_REVIEW**；5/5节、11页、累计37次请求。content/compile/layout/security PASS，math/policy NEEDS_REVIEW；未提交教师审核。源码ZIP在新目录Windows重编译PASS，11页文字/链接数一致，见 [记录](live-zip-recompile-20260920-043108.json) |
| CH02 无穷级数，完整真实生成 | **IN_PROGRESS / 当前FAILED**；S02真实恢复已核验，后续S03因 `INVALID_MODEL_JSON` 失败，累计19请求；整章仍未完成 |
| CH03 函数极限与连续，完整真实生成 | **IN_PROGRESS / 当前BLOCKED**；局部修复预算耗尽，累计27请求；不以已有Beamer应用链代替 |
| 真实产物只读浏览器验收 | **NOT_RUN**；8766尚未启动，待主流程通知，不混用mock E2E作为真实产物验证 |
| 三章 × 默认/FDU课件 | 六组真实 Windows 编译及来源检查 PASS，522/522页已渲染；几何仍 NEEDS_REVIEW，教师审核 NOT_RUN |
| 教师数学与逐页视觉验收 | **NOT_RUN**；任务保留待复核，不由 agent 代签 |
| 最终总体结论 | **IN_PROGRESS / NEEDS_REVIEW**；待主任务补正式三章及最后定向测试、运行状态 |

工程、安装和启动步骤见 [README](../../README.md)。六份 PDF、主 TeX、可重新上传的完整 v2 ZIP、编译清单与逐文件哈希见 [DELIVERABLES.md](DELIVERABLES.md)。所有产物为本地草稿；程序运行不依赖 Codex 会话、Node、Docker、WSL 或 Redis。

参考资料、首次失败与修复后的具体差异见 [改进对照表](IMPROVEMENT_COMPARISON.md)。本轮没有模型权重训练；章节材料用于风格参考、来源核对与实际回归。

## M0—M5 实施与验收映射

| 阶段 | 已连接的实际功能与证据 | 验收边界 |
|---|---|---|
| M0 审查与参考资料 | 完整规范阅读、确认无既有工程、核对三章主 TeX/PDF/主题/资源；第二轮新增8章全稿及17书目审计；[首轮M0](../M0_result.md)、[全稿审计](source_audit.md) | 资料齐全不等于数学原稿无误；完整CH03应用验收再次核对53个原文件哈希未变 |
| M1 本地界面与工作流 | 两输入、结构化选项与末项自定义、计划revision/hash/diff、显式确认、幂等执行、删除/新增、后台队列、刷新恢复、下载、逐页审核、用户预算与部分稿；[六例真实浏览器](ui-final-six-20260920-040716/README.md) | 模型为MOCK；实际编译/浏览器。六例快照早于最后parser修复，不能替代真实教学能力或教师审核 |
| M2 专题讲义与模型 | 指定兼容API、文本/SSE、逐节生成/核算/局部及全局审阅、定向修复、引用与编号、失败恢复；[真实smoke](live-lectures/smoke/comparison.md)、[CH02 S02真实恢复](CH02-S02-live-recovery.md)、[核算协议](calculation_protocol_checks.md) | 真实smoke已到待复核；正式三章仍IN_PROGRESS；小节通过、SymPy与模型审阅不是整章结论或一般形式化证明 |
| M3 原讲义转Beamer | 无损来源单元、保留证明与关联解答、精确授权删改、默认/FDU、显式书目补齐及原件保护；[六组比较](beamer_comparison.md)、[完整CH03应用链](full_beamer_app-v2/report.md) | 六组编译/来源PASS与完整应用链通过不等于教师认可；不同基线和页数不当作教学评分 |
| M4 布局与检查 | 合法字号、按语义分组/拆页、完整三态目录、全部overlay渲染、隐藏overlay几何处理、逐页人工入口；[目录容量](directory_capacity.json)、[布局探针](../layout_probe_validation.md) | 自动几何有复核项；模型视觉未验证，教师全页审核NOT_RUN |
| M5 独立运行与交付 | Windows脚本、独立workspace、SQLite恢复、真实HTTP下载、完整ZIP干净目录重编译；[运行记录](runtime-default.json)、[517项最新本地回归](local-final-20260920-041926.md)、[交付清单](DELIVERABLES.md) | 应用可运行；三章真实教学生成与人工验收未全完成，不能标M5全部PASS |

阶段基线仍保留在 [M1](../M1_result.md)、[M2](../M2_result.md)、[M3](../M3_result.md)、[M4](../M4_result.md)、[M5](../M5_result.md) 和 [首轮最终报告](../FINAL_ACCEPTANCE.md)。这些历史报告中的缺密钥、缺书目条件不代表第二轮最新状态，也没有被倒改成通过。

## 分层测试与代码快照

环境为 Windows 11、项目 Python 3.12.4、TeX Live 2024 XeLaTeX、Microsoft Edge。以下数量来自对应执行，不能把重叠专项相加成唯一测试总数。

| 类别 | 实际结果 | 证据与范围 |
|---|---|---|
| 最后parser与同证据身份修复后的完整本地回归 | **517 passed，1 deselected，0 skipped，207.24秒** | [报告](local-final-20260920-041926.md)、[日志](local-final-20260920-041926.log)、[JUnit](local-final-20260920-041926.xml)、[稳定来源快照](local-final-20260920-041926.json)；含20项实际Windows编译，104份文件前后SHA一致。E2E目录未收集，排除1项真实API用例 |
| 局部恢复与预算交付修复后的完整本地回归 | **498 passed，1 deselected，0 skipped，205.87秒** | [日志](local-final-20260920-040124.log)、[JUnit](local-final-20260920-040124.xml)、[稳定代码快照与逐项结果](local-final-20260920-040124.json)；含19项实际Windows编译。执行所有顶层本地测试，E2E目录另测、未收集；1项真实API用例被排除 |
| 此前的三章修复本地快照 | **369 passed，6 deselected，0 skipped，178.15秒** | [日志](chapter-final-full-20260920-030902.log)、[JUnit](chapter-final-full-20260920-030902.xml)、[前后稳定代码快照](chapter-final-full-20260920-030902-metadata.json)；包含18项真实Windows编译，模型仍为MOCK/替身，真实API与E2E另列 |
| 上一轮真实失败快照 | **360 passed，1 failed，6 deselected** | [记录](chapter_fixes_validation.md)；并发初始化 SQLite WAL 锁冲突真实失败，随后修复事务回滚及有界重试；[并发验证](migration_concurrency_validation.md)保留原失败及线程/独立进程复测。不能倒改上一轮为全过 |
| 第二轮完整本地快照 | **250 passed，6 deselected，0 skipped，133.14秒** | [日志](final-local-20260920-022414.log)、[JUnit](final-local-20260920-022414.xml)、[代码/环境/节点元数据](final-local-20260920-022414-metadata.json) |
| 其中 Windows 编译 | **14项实际执行**，包含在上述250项内 | 中文路径、失败/取消、跨节与公式引用、PDF链接、ZIP复编译、PDF占用、真实已捕获片段、CRLF/书目及合成流程；非额外14项 |
| 独立五例浏览器快照 | **5 passed，55.40秒，0失败/跳过** | [日志](final-ui-20260920-022409-905.log)、[JUnit](final-ui-20260920-022409-905.xml)、[报告](final_ui_validation.md)；真实编译及PDF/ZIP/每页PNG下载，五份console均为空 |
| SQLite修复后的五例浏览器复测 | **5 passed，54.34秒** | [报告与代码快照](ui-postfix-20260920-031401-721/README.md)；真实Edge与Windows编译、模型为MOCK；不包含随后正在集成的严格局部修复状态 |
| 局部恢复/预算交付后的全部浏览器用例（早于最终parser修复） | **6 passed，79.12秒** | [报告](ui-final-six-20260920-040716/README.md)；旧5例及新增预算恢复1例，102个源码/测试/锁文件哈希稳定；模型MOCK、实际Edge/Windows编译/文件下载，6份页面错误日志为空。尚未在最后parser/同证据身份补丁后重跑，不能冒称覆盖最终517项代码快照 |
| parser合法AMS text作用域与同证据身份专项 | 先红8 FAIL/6 PASS；其后98 PASS/1 fixture FAIL；修正后37 PASS；身份边界另5 PASS | [诊断与完整记录](text_math_scope_validation.md)。合法S05 U02表格正文逐字不变，独立实际Windows编译1页PASS；旧拒绝和计数保留。后续已合入上述517项完整快照，数量不累加 |
| 快照之后：旧失败恢复边界 | **68 passed，26.14秒** | [日志](legacy_boundaries_final.log)、[JUnit](legacy_boundaries_final.xml)；零修复预算、最新checkpoint、旧seed规范化后比较非目标单元等 |
| 快照之后：末尾答案回链 | **6 passed，含实际Windows编译/aux/PDF链接** | [报告](answer_references/report.md)；只影响之后生成稿，未重建已交付5页smoke |
| 上述两项补丁合并后的定向回归 | **75 passed，43.18秒** | [日志](final-targeted-20260920-023221.log)、[JUnit](final-targeted-20260920-023221.xml)、[稳定代码快照](final-targeted-20260920-023221-metadata.json)；含真实Windows编译、回链与CRLF检查；不累加为唯一总数。正式三章随后发现的引用/缺答案修复另行记录 |
| 更早本地快照 | 210 passed，6 deselected | [日志](final-local-20260920-020122.log)；仅历史，不累加 |
| Windows脚本工作区参数 | PS5.1中25条模拟断言PASS | [报告](ui_workspace_script_validation.md)；启动命令使用替身，不伪称真实应用启动 |

本地快照显式设置 live=false、API key为空、streaming=false，不导入Windows User环境、不调用供应商。旧快照6项deselected为5个独立E2E及1个真实API条件用例；498项与最新517项运行只收集顶层本地测试，因此只排除1项真实API，E2E目录另外执行，不能比较排除数量来推断覆盖增减。517项中的20个Windows节点含预期失败诊断、取消和越界阻断：测试通过不等于每个负例编译成功。两条已锁依赖弃用警告保留，不是数学/视觉通过结论。第一轮实际安装、启动→停止→恢复、中文路径、PDF占用和源码包重编译记录见 [UI与脚本](../ui_windows_validation.md)、[编译与数学](../compiler_math_validation.md)、[文件交付](../delivery_validation.md)。

严格局部修复及三章实际失败链的专项见 [恢复验证](local_recovery_validation.md)；预算与部分稿的55项API/迁移及1项真实Edge专项见 [预算验证](budget_validation.md)。专项与完整回归有重叠，不累加为唯一总数。新增预算表保留未知历史状态，禁止默认120隐式扩展旧60；四个真实run已按归档测试清单核验恢复原60上限，原计数21/26/11/22、审批、计划、jobs、产物和reviews均未改变，且未执行模型，见 [备份及迁移记录](budget-migration-20260920-040218/migration.json)。

最后解析器修复解决外层数学中合法 `\text{$\varepsilon$--$N$ 定义}` 被误拒的问题：仅对已知AMS文本参数建立独立数学范围，保留字节和原始证据，不将被拒提案自动采纳。审阅身份同时纳入实际确定性检查，而不把归一化历史、坐标或subset元数据变化当作新证据；旧parser FAIL→新PASS可以携原问题重评，完全相同正文和检查结果下的空审阅/no-op补丁仍不能清除未决疑点。独立1页Windows产物仅证明捕获表格的编译问题已修复，不是S05数学审核或整章通过，详见 [text_math_scope_validation.md](text_math_scope_validation.md)。

## 真实 API、校准与预算

密钥经用户授权在本机隐藏输入，保存为 Windows User 环境变量；应用仅从环境读取，不读 `.env` 或聊天值，不把密钥写到源码、命令参数或浏览器。启动脚本导入当前进程尚未设置的API/模型/streaming变量，已有进程值优先。证据：[配置记录](environment_configuration.json)、[文本检查](provider_initial_check.log)、[SSE探针](streaming_probe.json)、[最新能力记录](provider_streaming_capabilities.json)。文本与SSE已实际 supported；vision、tools和服务端json_schema能力仍 untested。客户端Pydantic schema验证通过不等于服务端json_schema能力已验证。

指定网关的长非流式请求曾在约60秒返回504；保留原失败后启用已经验证的SSE。当前配置 `MATH_AGENT_LLM_STREAMING=true`，其它新安装的设置默认false；配置方法见README的 `Configure-LiveApi.py --streaming`。能力探针成功没有被当作完整讲义通过。

中性编号的数学审阅校准进行了 **3次真实请求、3个已知错误+3个正确对照**。ε量词错误、把通项趋零当成收敛充分条件、极限不等于点值却声称连续，均被标为blocking；正确对照无blocking/review误报，TP=3/FN=0/TN=3/FP=0。预期答案只保存在本地，模型接收中性U01/U02并交替顺序。此前带bad/good标识的3次初测可能泄露预期结论，不能作为另外3个独立样本累加。见 [中性复测](reviewer-calibration-neutral/README.md)、[结果JSON](reviewer-calibration-neutral/summary.json) 和 [初测记录](reviewer-calibration/README.md)。这是人工编写的基础小样本校准，不是随机盲测准确率、完整课程正确率、模型权重训练或形式化证明。

审阅规则v2和真实答案渲染上下文加入后，另在独立目录完成 **3次真实最终复测**，同一六单元题集再次得到TP=3/FN=0/TN=3/FP=0，3个错误均为blocking。见 [最终版本说明](reviewer-calibration-final/README.md)、[结果](reviewer-calibration-final/summary.json)。这是相同题集的回归，不是新增独立样本；旧版本结果与新结果不混合。

审阅规则v3又完成 **2次真实课程范围回归**：同一份正确证明，在明确禁用上/下确界的课程中检出违规，在仅排除高阶公理体系而允许引用明示基础性质的课程中没有误报。见 [范围回归](foundation-scope-calibration/README.md)。这不是新的独立数学准确率样本；v2的六单元回归不能冒充v3完整校准。

真实讲义驱动预算为 **每run最多60次、本轮总共240次**，发送前持久计数；基础校准9次、课程范围回归2次（合计11次）与能力探针3次另列，不混入讲义驱动预算。smoke固定快照累计21次（包括失败/重试），正式三章运行中的最新计数见 [benchmark_state.json](live-lectures/benchmark_state.json)。供应商未给价格，费用为null，缺失token不算零；不按次数或已知token推算费用，超时/崩溃边界可能已经计费。

## 两节真实 smoke 与恢复证据

真实run为 `426866cf71d2437bb17b54ac801a8c18`，同一计划revision 2、同一审批hash `9e57a417de22ea8854850c2e7554dbb6603347d7547f552813e76f6cca122a2d` 在恢复后继续使用，没有伪造教师review。2/2节已检查，生成5页；累计21次真实请求，包括前期失败。实际自动维度为 content/math/compile/layout/security PASS、policy NEEDS_REVIEW；选择落实2项PASS、2项NEEDS_REVIEW。总比较仍NEEDS_REVIEW，任务为AWAITING_USER_REVIEW，`reviews`为空。

全局审阅实际指出S01两个单元遗漏正整数无上界/阿基米德前提；系统保留问题和旧草稿，仅允许定向修复目标单元，重新检查受影响及后续章节和节间接口，再做全文编译/审阅。该真实任务的全局修复 `rounds_used=1`、`phase=validated`。证据：[比较报告](live-lectures/smoke/comparison.md)、[请求与耗时](live-lectures/smoke/request_metrics.json)、[持久任务与审批](live-lectures/smoke/run_snapshot.json)、[实际修复状态](../../workspace/iteration2-live/runs/426866cf71d2437bb17b54ac801a8c18/global-repair-state.json)。

该 smoke 的实际源码 ZIP 已在全新目录通过 Windows XeLaTeX 两遍重编译：5页、逐页提取文字及链接数量与交付 PDF 一致，解压源文件哈希未变，真实 API 调用0。见 [独立重编译记录](live-zip-recompile-20260920-034007.json)。首次验证脚本误用了项目未安装的 fitz，未进入编译；[失败日志](live-smoke-zip-recompile.log)保留，随后改用既有 pdfplumber 依赖通过，不倒改首轮结果。

旧计划依赖错误、无效JSON、网关504、重复教学环境、审阅范围错位、核算协议缺失、编号公式锚点错误和全局前提问题都有相应记录。归一化、未审草稿复用和旧故障恢复不把 unchecked 当 checked；旧问题不通过重复抽一次审阅而消失。数学疑点不会因编译通过被忽略。见 [内容诊断](live_content_diagnosis.md)、[草稿恢复](draft_recovery_validation.md)、[公式标签](labeled_equations/comparison.md)、[全局恢复](global_repair_validation.md) 及 [不可覆盖尝试档案](live-lectures/smoke/attempts/)。

## 三完整章恢复快照（不是最终验收）

CH02 S02 的真实答案恢复与严格局部补丁链已独立只读核验：**64项证据断言通过、30个来源文件审计期间SHA一致**。新答案提案完整沿用旧 `repair-1` 已接受稿，先保留20个原单元及3条核算、追加3个准确关联的答案和1条核算，再由严格补丁只删除U18/U19/U20题干的内嵌答案后缀。非目标20单元、全部4条核算及metadata保持；旧拒绝未采纳，累计3次接受/4次提案/1次拒绝保留。各原题累计接受修改2次、新答案各1次，请求从旧11连续到S02完成16次，原60预算及批准计划不变。

S02本轮五次真实请求均有HTTP200、完整SSE、schema验证和保存输出哈希匹配：reviewer_math实际prompt v3，repair_missing_answers与repair_local_patch实际v1。小节检查点记录4项SymPy PASS、双遍Windows XeLaTeX PASS、6页累计S01+S02草稿。审计没有再次调用API、重编译或写数据库；教师NOT_RUN，也不是完整章PDF或最终数学结论。见 [S02报告](CH02-S02-live-recovery.md)、[结构化证据](CH02-S02-live-recovery.json)。早期U14 warning及未知旧reviewer prompt身份仍保留说明，不以最终模型空问题列表冒充教师裁定。

完整三章仍为 **IN_PROGRESS**。本次文档更新使用主流程回报的状态：CH01 retry3 active；CH02 S03 `INVALID_MODEL_JSON`、累计19请求；CH03局部修复预算阻塞、累计27请求。主流程继续处理，这些计数是本次汇总快照，后续以持久运行记录为准。最后parser修复、S02小节成功和其它局部产物不能补写整章PASS。8766尚未启动，真实产物只读浏览器验收继续NOT_RUN。

## 三章课件、完整应用链与源包交付

| 数据集 | 默认/FDU物理页 | 实际结果 |
|---|---:|---|
| CH01 | 77 / 77 | 编译PASS、来源PASS、全页渲染；人工未审 |
| CH02 | 76 / 76 | 编译PASS、来源PASS、全页渲染；人工未审 |
| CH03 | 108 / 108 | 编译PASS、来源PASS、全页渲染；人工未审 |

六组共522页，来源为实际原讲义，缺失引文从新增完整原稿复制，原文/行号/hash有provenance。它们是确定性课件转换，没有调用模型API。正文自适应正常字号、合法组合证明步骤、保持完整目录；FDU原sty不改，适配层明确展示当前section导航。页数与原手工54/51/93页不同，不通过删正文或压小字号强行追平。完整比较见 [beamer_comparison.md](beamer_comparison.md)。

另对**完整CH03**执行实际 `Service.attachments → propose/Worker → benchmark_driver确认 → Worker构建 → HTTP下载`：run `e19924249d254adaa665752ed66504dc`，7节/104来源单元、93逻辑帧/108物理页、7个检查点。124个产物经进程内TestClient实际HTTP下载均200且SHA与数据库一致，其中108/108页PNG连续完整；这不是TCP/浏览器测试，也没有用直接调用转换器冒充应用流程。provider为mock、模型请求0，编译/来源PASS、数学/布局NEEDS_REVIEW，数据库无人工review。见 [应用链报告](full_beamer_app-v2/report.md)、[完整机器记录](full_beamer_app-v2/report.json)。

原53个文件（原三章51份+新增完整TeX/PDF）SHA-256复核全部未变，记录在上述JSON的 `original_sha256` 与 `originals_unchanged=true`；第一章第三次恢复期间再次只读复查 [53/53 PASS](originals-recheck-20260920-retry3.json)。书目选项默认false，UI显式选择后生成独立派生副本；原upload、原快照与完整原稿保持不变，`plan.source_enrichment`进入计划hash和确认。来源文献未另行联网核实。

六份v2 ZIP逐成员CRC/SHA核对通过；JSON清单旁置，ZIP含真实主TeX、sty/适配及必要图片，可由应用安全解压。CH01/default、CH03/FDU从新解压目录真实两遍XeLaTeX通过，77/108页及全部页提取文字与基线一致，解压源码未改。完整CH03应用实际下载的ZIP也另作108页干净复编译PASS。[交付索引](DELIVERABLES.md)、[六包验证](../../workspace/iteration2-delivery/delivery-20260920-020236.json)、[应用源包复编译](full_beamer_app-v2/zip-recompile.json) 保留产物与日志。

## 已知限制、失败证据与收尾字段

- **教师审核未执行**：自动几何、模型审阅、agent抽看截图或成功下载，都不等于数学教师与逐页视觉验收。原稿习题章号、经济应用/难度/自定义语义、字体替代与靠近正文边界等仍需核对。
- **数学检查有限**：有界SymPy请求可给符号核验或数值抽查；未核算、条件不足及数值证据不是证明。模型审阅校准的小样本结果不能外推为普遍正确。
- **能力边界**：真实文本/SSE已验证；vision/tools/服务端json_schema未测，页面图片未交给第三方视觉模型。没有模型权重微调或盲测课程准确率声明。
- **原生模式边界**：trusted_local不是文件系统/网络沙箱；isolated尚未实现。当前只监听loopback，不是公网、多用户或不可信TeX部署；见 [迁移边界](../server_migration.md)。
- **失败保留的实际局限**：最早一次无效JSON仅保存响应hash、schema错误及请求/usage信息，没有保留完整原始无效响应，不能声称可还原该原文。后续有效候选、检查报告、修复前后正文、编译日志与尝试档案均保留。
- **历史失败没有覆盖**：首次完整CH03因CRLF二次转换形成CRCRLF而BLOCKED，旧输入/审批没有补写；修正字节写入后新建v2任务。早期E2E过宽断言、书目换行断言和首版ZIP含JSON被拒绝均保留原日志。首版ZIP后续通过独立解压不充当上传兼容证据，最终v2重新走应用解压器。
- **密钥审计有范围**：[secret_storage_audit.json](secret_storage_audit.json) 在当时7553个源码、文本日志、报告、TeX及SQLite字节中未匹配当前值；明确排除了虚拟环境/git/cache和压缩文件，不将这项结果扩大成未执行的全盘审计。

待主任务收尾：填入正式CH01/CH02/CH03各run的最终状态/页数/真实请求与检查报告，补入最后补丁合并后的定向结果，核对最终运行服务及产物链接，再决定是否结束本轮工程验收。**只要人工审核未执行，其字段继续NOT_RUN；只要三章尚未完成，其字段继续PENDING。**
