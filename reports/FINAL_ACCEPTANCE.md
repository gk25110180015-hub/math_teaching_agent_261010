# Windows 11 本地交付与最终验收记录

记录日期：2026-09-20（Asia/Shanghai）。**独立应用已实现并实际启动；M5 全部验收尚未通过。** 缺少新的 API 环境密钥、原讲义书目条目和教师审核，不能用 mock 或成功生成 PDF 代替。

## 交付与运行

入口：<http://127.0.0.1:8765>。本次实测首页 HTTP 200，健康检查 `status=ok`、独立 `worker.alive=true`，见 [runtime_verification.json](runtime_verification.json)。服务及 worker 在后台隐藏窗口运行，退出 Codex 或关闭网页不作为任务取消信号。

工程在 `D:\研究生阶段\数学教学agent\math-teaching-agent`。浏览器、FastAPI API、SQLite 持久计划/审批/队列、独立 worker、模型适配、编译、数学/来源/页级检查、受控下载均已连接。提供讲义生成和 TeX/ZIP 转 Beamer 两条工作流，支持默认与实际 FDU 模板。

- 启动/停止/配置说明：[README](../README.md)。已安装项目内 `.venv`、项目内 uv，依赖使用 `uv.lock`；无需依赖 Codex、Node、Docker、WSL 或 Redis。
- 演示产物：[交付样例说明](../deliverables/README.md)。PDF、主 TeX、完整源码 ZIP、质量报告均来自实际工作流。它们是演示草稿，不是已通过教师审核的教学材料。
- 三章新转换草稿：[reference_matrix.md](reference_matrix.md)，每组实际路径和哈希在 [JSON](reference_matrix.json)。缺书目的草稿仍可供诊断，不能发布为合格课件。
- 恢复：保留 `workspace/agent.db`、`workspace/inputs`、`workspace/runs` 与 `workspace/b`，重启后任务恢复；失败后沿用原审批重试。输入变化须新任务重新确认。

服务只监听 127.0.0.1。进程身份及日志位于 `workspace/runtime/local-processes.json` 和 `workspace/logs/`；[启动日志](final-startup.log) 已保存。使用 `scripts/Stop-Local.ps1` 仅停止本工程记录且身份匹配的进程树。

## M0—M5 的实际结果

| 阶段 | 已完成与证据 | 验收边界 |
|---|---|---|
| M0 | 完整阅读1522行规范；无既有工程；检查三章主 TeX/PDF、FDU主题与图像依赖；51原件清单/hash；Windows工具链审计 | 文件齐备不等于原数学/书目正确；缺引用在实际编译时发现 |
| M1 | 计划版本/hash、选择/自定义、精确删除、确认、幂等执行、失败恢复、worker租约/取消、界面闭环 | 合成/mock测试，不是供应商验收 |
| M2 | 指定兼容API适配、严格JSON、有限重试/预算、逐节写作与复核、SymPy受限AST、前后节引用、实际编译 | 真实API端到端 BLOCKED；没有通用数学证明保证 |
| M3 | 无损源跨度、明确题解关联、安全ZIP、双模板、实际输出独立来源核验 | 六组源转换来源PASS；缺书目导致编译验收FAIL |
| M4 | 四档字号、语义拆页、pause/全部overlay、实测模板probe、全部物理页PNG/几何检查、人工审核入口 | 模型视觉NOT_RUN；教师视觉NOT_RUN；probe不是全模板形式化校准 |
| M5 | 独立启动、PS5.1/7脚本、真实浏览器、中文路径、进程恢复、PDF占用、源码ZIP干净目录重编译 | 完整三章教学验收 BLOCKED；M6仅迁移边界文档 |

阶段详表：[M0](M0_result.md)、[M1](M1_result.md)、[M2](M2_result.md)、[M3](M3_result.md)、[M4](M4_result.md)、[M5](M5_result.md)。T01—T60逐项范围与未测项见 [test_matrix.md](test_matrix.md)。SQLite采用原生编号SQL迁移，而非SQLAlchemy/Alembic；并发迁移、事务、租约与恢复已实际回归。

## 分层测试：不混用证据

环境：Windows 11 25H2 / build 26200.9457，Python 3.12.4，TeX Live 2024 的绝对路径 XeLaTeX，Microsoft Edge。所有测试通过数均来自本轮记录，不累加前轮重复测试。

| 类别 | 本次结果 | 证据/限制 |
|---|---|---|
| 本地逻辑、mock协议、状态、安全、Windows编译/交付集成 | **101 passed，5 deselected**，70.83秒 | [日志](final-local-tests-v3.log) / [JUnit](final-local-tests-v3.xml)；排除4浏览器及1真实API条件用例 |
| 真实浏览器 E2E | **4 passed**，41.42秒 | [日志](test-runs/20260920-003846-307-browser.log) / [JUnit](test-runs/20260920-003846-307-browser.xml)；mock内容+真实Windows编译/下载/全页PNG |
| 真实 API 条件检查 | **1 skipped** | [日志](real-api-final.log) / [JUnit](real-api-final.xml)；环境密钥/live开关缺失，未发供应商请求 |
| 三章×双模板真实源转换 | 六组来源PASS，586/586页实际渲染；无OVERFULL、无几何blocking | 六组编译验收均FAIL：原文未定义文献引用；几何仍NEEDS_REVIEW |
| 教师数学与逐页视觉验收 | **NOT_RUN** | 没有把程序点击、开发诊断抽样看图或页面渲染当成人工通过 |
| 真实模型视觉 | **NOT_RUN** | 能力未验证，未向第三方发送页面图片 |
| 完整文件/网络隔离 | **NOT_RUN / 未实现** | 当前trusted_local明确不是沙箱；isolated不可用即阻塞 |

本地最终命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -m 'not e2e and not real_api' -q --basetemp workspace\tfinal4 --junitxml reports\final-local-tests-v3.xml
.\scripts\Test-Windows.ps1 -Suite browser
.\.venv\Scripts\python.exe -m pytest -m real_api -q --basetemp workspace\tlivefinal --junitxml reports\real-api-final.xml
```

重跑时使用新的临时目录及日志名，保留旧失败产物。汇总机读记录：[acceptance_matrix.json](acceptance_matrix.json)。两条依赖弃用警告保留在日志中；当前未造成测试失败。

Windows实测覆盖中文/空格路径、原生TeX读写最低限制、无限循环TeX取消且不杀无关进程、中间overlay真越界阻塞、旧PDF不冒充新构建、PDF被占用时新版本成功、干净中文目录ZIP重编译、秘密不进入子进程或源包、真实worker子进程终止后租约恢复。详见 [编译与数学](compiler_math_validation.md)、[交付](delivery_validation.md)、[UI与脚本](ui_windows_validation.md)、[布局探针](layout_probe_validation.md)。

跨节引用用合成模型执行了真实完整工作流：前文引用计划中已登记后文定理，局部原编译FAIL保持不变，单独记待全文验证；全文成功后读取实际 `.aux` 核对编号。未知标签、未兑现的登记标签、缺书目都不能套用该例外。它不代表真实模型长讲义已测试。

## 三章参考验收与原件保护

没有覆盖任何原始资料。51个原文件的最终SHA-256核对全部一致。三个同名讲义用 dataset/path/hash区分；三个FDU主题原件同一哈希，复制使用，适配层单独维护。

| 章节 | 默认模板页数 | FDU页数 | 编译阻塞 |
|---|---:|---:|---|
| 第一章 | 88 | 88 | `BradyWeil` 文献未定义 |
| 第二章 | 78 | 78 | `NCBISteadyState` 文献未定义 |
| 第三章 | 127 | 127 | `NCBIEnzyme`、`BradyWeil` 文献未定义 |

对应原稿行号为第一章314、第二章722、第三章650/1388。未找到相应bibitem/bibliography。系统保留原引用，没有编造文献或删正文以过检。需要在新的输入副本补齐真实条目后新建任务验收。精确证据见 [原资料动态问题](reference_dynamic_findings.md)。

Beamer隐藏overlay曾造成页外字符误报。修复只接受同frame另一overlay的精确字符/字体/字号/位置对应与PGF固定平移，记录原/校正bbox和两页hash；不对未知越界放行，实际中间overlay溢出回归仍阻塞。真实大TikZ坐标、长列表、编号标签、空布局frame等问题已修复且保留旧失败版本。详见 [几何诊断](reference_geometry_diagnosis.md)、[overlay回归](pdf_overlay_visibility_validation.md)。数学下标的小字号、正文边界接近和字体替换仍列复核，不声称教师已通过。

原参考PDF的233页也已全渲染，但只作为原样基线，不算新产物验收。

## 外部条件与仍需人工核对的内容

1. **API**：默认接口 `https://oneapi.advancedsolver.com/v1/chat/completions`，模型 `gpt-6-astra`。只读取环境变量，不读聊天密钥、不读 `.env` 文件、不在网页接收密钥。请撤销对话中已暴露的值，按README以隐藏输入设置新 `MATH_AGENT_API_KEY` 和 `MATH_AGENT_LIVE_API_ENABLED=true`，重启后运行最小连通检查，再分别执行数列极限、函数极限、导数与微分的真实讲义验收。
2. **书目**：补齐上述原稿文献，上传新的可信TeX/ZIP并确认新计划。当前六组草稿均保持BLOCKED，不能靠人工“忽略”按钮消除已知编译错误。
3. **教师验收**：逐页检查实际数学、论证连贯性、难度/经济应用/自定义比例、公式下标及高风险几何；界面记录每页和质量报告hash的用户审核。任意未知TeX、不可安全拆开的长公式/等式链或过长标题可能阻塞，系统不会用截图、过小正文字号或删数学内容兜底。

这是可信单机工具。公网、多用户、不可信上传的隔离与权限体系尚未实现，不能当作已部署服务；M6仅有 [迁移边界](server_migration.md)。

## 失败证据与恢复

保留初次依赖/网络失败、Windows长路径失败、旧来源拆分失败、过宽E2E断言、隐藏overlay误报及后续修复记录。早期“4 passed”仅验证状态的范围已在 [E2E纠正说明](e2e/ACCEPTANCE_NOTES.md)明确撤回，不当作业务通过。

最后新增失败诊断下载测试曾因未初始化会话返回403，`final-local-tests-v2.log`记录100通过/1失败；修正测试按真实浏览器先建立会话后，v3为101通过，未放宽访问控制。失败信息经过脱敏，`failure_diagnostic.json`可按artifact_id下载；详细源码/编译日志在本地版本目录，审批及成功检查点保留。

若同一输入失败，修复运行条件后“重试”；输入/条件/内容计划变化则新任务或新计划重新确认。外部API响应边界发生崩溃时可能重复计费，不能承诺供应商调用恰好一次。
