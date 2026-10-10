# 第四章转换故障修复与验证（2026-09-26）

用户任务 `e53fd34585fb4bc9af2a85fd994d610a`，原 job `ccd8a766f61c454b931dd8fadb98c371`。

修复已部署，原 job 第 4 次构建完成，生成 209 页课件，当前状态为 `AWAITING_USER_REVIEW`（等待逐页复核）。打开 http://127.0.0.1:8765，刷新并选择“第四章导数.tex”即可查看和下载，无需重新上传或确认计划。教师审核仍未执行。

## 原因与代码

原任务第 3 次失败停在 compile.global。实际 B-16 原因是第四章 U0116/U0123 的 TikZ 图中文字使用 `\scriptsize`，并非模型超时或 API 失效。之前的通用错误只要求重试，未指出具体位置，原输入不变时重试必然再次阻塞。

修复了原稿命名字号到允许四档字号的保真适配、enumitem 列表边距与 Beamer overlay 参数的冲突、嵌套证明/解答及列表尾部正文的连续拆页，并调整溢出后的第二排版候选。数学公式不改写，不删除内容，任意整体缩放仍拦截。字号/边距适配位置、原文哈希和替换内容随 `presentation_adaptations.json` 交付。

讲义与 Beamer 共用的 QUALITY_BLOCKED 现在给出规则、单元、可获得的源码位置和处理建议；网页先展示可读原因，原始诊断可展开。Markdown 质量报告包含具体问题，重复问题去重。讲义生成不使用 Beamer 的四档字号门禁，但共用错误反馈和恢复路径已测试。

修改的生产文件：

- [beamer.py](../../src/math_agent/beamer.py)
- [pipeline.py](../../src/math_agent/pipeline.py)
- [quality_diagnostics.py](../../src/math_agent/quality_diagnostics.py)
- [app.js](../../src/math_agent/web/static/app.js)

## 验证分层

| 类别 | 实际结果与边界 |
|---|---|
| 针对性本地回归 | [52 PASS](quality-targeted2.xml)。模型/失败编译用例使用 mock；并未把它们计作真实模型教学验证。 |
| 完整隔离本地回归 | [1134 PASS、0 FAILED、0 ERROR、0 SKIP](../iteration4/local-full-20260926-172749-629dc90e.json)，1 项真实 API deselected。显式排除真实 API 与 E2E；包含 21 项 Windows 编译标记用例，预期失败/取消仍按各用例断言解读。测试前后源码哈希一致。 |
| 实际 Edge 网页 | [6 PASS](edge-resumed.xml)：讲义生成、TeX 上传、原稿保留、删除/新增授权、失败重试、具体错误提示、文件下载；模型 mock，编译为实际 XeLaTeX。 |
| 第四章真实材料 / Windows | [隔离 p4 编译](../../workspace/q0926/p4/compile.json) PASS、[来源保真](../../workspace/q0926/p4/render.json) PASS、[全部 209 页渲染和几何检查](../../workspace/q0926/p4/inspection.json)完成，无 blocking 页外裁切。字体替代和版面边界提示保留为 NEEDS_REVIEW。 |
| 真实 API | 首次直接 pytest 继承本机 live 环境，实际执行了 `test_live_provider_opt_in`，最小“只回复 OK。”连通探针 2.912 秒 PASS，见 [JUnit](full-resumed.xml)。该用例未保存最终路由/尝试数，不能据此声称三个模型分别通过。本轮未进行真实 API 讲义生成/数学教学验收。 |
| agent 视觉检查 | 已查看隔离 p4 中受影响的 21 页渲染图：19、20、34—36、70—71、110—117、132、140、152、206—208。未见此前越页裁切；并未查看其余全部页面，图示标签位置仍需教师检查。 |
| 教师数学 / 视觉验收 | NOT_RUN；没有提交任何人工 review，不将自动检查当作教师验收。 |
| 原任务恢复 / 下载 / ZIP 干净编译 | [PASS](production-recovery.json)：原 job attempt 3→4，209 页；227 个下载文件逐一通过哈希核验；下载源码包在独立目录实际 Windows 重编译 PASS，209 页全文与交付 PDF 逐页相同。审批、输入、51 个旧文件保持不变；该任务模型请求数仍为 0，无人工审核提交。 |
| 已部署原任务 / 实际 Edge | [PASS](production-ui5/report.json)：209 项页面预览、无错误面板、无重新确认按钮；按 artifact_id 下载本次构建的 PDF、TeX、ZIP、质量报告和适配报告并核对哈希。展开第 20、132、140、208 页并验证图像加载，截图已由 agent 查看；无页面脚本错误，无修改请求。不是教师审核。 |

第 132 页面积图的 `(Δx)^2` 标签在较小矩形附近较拥挤，保留为教师视觉复核项；没有把字号增大后的全部图示宣称为排版完美。当前 math/layout 状态仍为 NEEDS_REVIEW，compile/fidelity/policy 为 PASS。

本次构建位于 `workspace/b/e53fd34585fb4bc9/vaec563e5d478`；PDF 为 `build-2/slides.pdf`，TeX 为 `candidate-2/slides.tex`，完整源码包为 `source_bundle.zip`。网页同时保留之前失败的同名草稿；本次 TeX 的 artifact_id 为 `b2c4312f7ed74a93b0230338bf2fae3a`，源码 ZIP 的 artifact_id 为 `3308bff2af2b4782b3e9cd9857ab969f`，其余映射见恢复报告。

[最终只读核验](final-verification.json) PASS：当前 218 个源码/测试/配置等快照文件与已通过的完整回归一致，8765/8766 服务及 worker 正常，原任务仍待教师审核，原审批未变、模型请求数为 0、人工审核记录为空。

## 失败和中断均保留

- [最初字号回归](font-red.xml)：11 FAILED，确认旧行为阻塞。
- [第一次拆页回归](quality-targeted.xml)：1 FAILED / 49 PASS；修复后 52 PASS，未删除测试或降低断言。
- p1—p4、各 probe 日志保留，包括列表兼容错误、页面溢出和 source interval 空白缺口的失败版本。
- 最初 full.log / edge.log 被额度中断，没有最终 XML；NOT_COMPLETED。
- [直接 pytest 轮](full-resumed.xml)：1119 PASS / 16 FAILED。16 个 mock 失败是继承真实流式/备用模型配置引起的分支差异；没有为了通过而关闭生产 fallback。此轮还包含上表记录的最小真实 API 探针。
- [第一次隔离全套](../iteration4/local-full-20260926-172116-e8575839.json)：1132 PASS / 2 FAILED。两项数学子进程未完成检查；[直接复现](math-investigation.json)结果正常，但原失败断言没有完整子进程证据，原因未确定。增加断言结果输出后重新执行整套，不将旧失败改写为通过。
- [before/baseline.json](before/baseline.json) 保留原审批及 51 份上传/旧产物的哈希；before/agent.db 为一致性 SQLite 快照。原资料不覆盖，历史任务状态不清零。
- [第一次生产网页核验](production-ui.log)因辅助脚本缺少 base_url，下载相对链接时报 Invalid URL；其 report.json 遗留 RUNNING，实际应按失败日志解读，不能计为通过。production-ui2/3 因保留的同名草稿导致定位不唯一而 FAIL；改用本次构建的 artifact_id 后 [production-ui4](production-ui4/report.json) PASS。最终 production-ui5 进一步展开预览并验证图像加载；前述失败与截图均保留。
