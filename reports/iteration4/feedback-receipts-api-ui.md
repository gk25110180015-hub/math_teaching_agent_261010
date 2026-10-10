# 本轮反馈逐项回执候选

该候选只增加 Service.get 的 `feedback_review` 字段及结果页展示，未修改生产源码、任务数据库、正文、审批或预算。需与 `math_agent.feedback_review` 的共享 schema/helper 同批部署。

当前候选为 `feedback-receipts-service.candidate.py` 与 `feedback-receipts-ui.candidate.js`，合并差异见 `feedback-receipts-api-ui.patch`，逐文件基线与候选 SHA 见 `feedback-receipts-api-ui-manifest.json`。

回执按最新 build job（时间相同时以 rowid 决定）、最新 `checks.rerun_requested`、当前批准计划 hash/revision 和原始 feedback 字符串的 hash 隔离。无反馈时新字段为 null，旧快照/客户端保留兼容性；新一轮空反馈撤回旧显示。API 不会回退到上一次有效结果掩盖本轮非法回执。格式及完整 F1… 覆盖使用共享 `FeedbackAssessment` 和 `extract_feedback_items` 验证；合法 `.answer` 单元 ID、讲义交付约束依据、无单元目标但有计划依据的范围外意见均保留支持。

界面显示“本轮最近一次反馈核查”、时间、回执阶段、逐项理由、引用单元与建议修改单元，并明确回执对应核查时的正文快照。状态映射为已满足、待改进、不适用、无法确认。invalid/transport_pending 只能展示未决说明，不冒作完成或正文修改。回执单独变化也进入页面轮询的变化判断；现有反馈草稿按 runId 保留逻辑不变。正文修订中的上次回执不称为当前正文结论，也不产生教师审核。

已执行的离线验证：

- 初始部署代码缺少回执字段，29 项新回归红测；随后扩大后的 32 项红测亦全部复现缺口。失败日志保留于 `feedback-receipts-validation/20260920-180207-373736` 和 `20260920-180830-3c6a5f`。
- 最新候选 68 项 API 回归通过，其中新增回执测试 34 项、既有反馈/工作流/自动复检 34 项。证据：`feedback-receipts-validation/20260920-180928-39ca78`，包含测试 SHA、共享 schema 候选 SHA、JUnit、日志、隔离包路径及生产 SHA 未变核对。
- 候选 JavaScript 的 `node --check` 通过。

同批六文件候选进一步联合验证 **70 项通过**，证据 `feedback-receipts-validation/20260920-181402-554d49`。其中两项新增集成由正式 TestClient recheck 请求产生真实事件，由 Pipeline 调用受控 mock 逐项评估：一项先给出 supported_improvement，仅修订 S02.U01，再对新正文评估为 satisfied 并由 GET 返回最新回执；另一项故意遗漏 F2，保留 invalid 回执及所有项目的未决原因，不修改正文。实际回执文件 SHA、当前 job/plan/feedback 归属、原审批/输入/请求计数和无教师签字均有断言。

这些是 mock/合成回执、真实 SQLite 与 TestClient 的测试，未执行真实模型 API、Windows 编译、真实 Edge 或教师验收。六文件生产基线前后 SHA 一致；完整 shared-helper 候选字节及 tests SHA 记录在联合测试的 context.json。

Pipeline 新增“先处理既有数学疑点，再做独立反馈评估”后，已对更新的六文件候选重新执行相同联合套件：**70 项通过，10.50 秒**，新证据 `feedback-receipts-validation/20260920-181704-246480`，未复用上一个 Pipeline 版本的通过结果。Service/UI 两文件获 chapter_quality_audit 独立只读审查通过，基于当前字节、AST、联合测试日志确认 job/plan/feedback 隔离、无旧回执回退及 UI 快照限定。当前两文件候选可供 root 与其余已审查候选统一部署；新 Edge 仍未执行。

新增 `tests/e2e/test_feedback_receipts.py` 已准备：真实 Edge 和 Windows 编译，使用 mock provider；验证 F1/F2/F3 回执、仅回执变化时的实际轮询刷新、未提交反馈草稿保留、刷新恢复、下一轮空反馈隐藏旧回执并保留历史事件；不提交教师审核。该新增浏览器测试尚未执行，不能复用上一版 13 项 Edge 的通过结果。本次新增后全量 E2E 共 14 项，应更新后续执行器的预期数量。
