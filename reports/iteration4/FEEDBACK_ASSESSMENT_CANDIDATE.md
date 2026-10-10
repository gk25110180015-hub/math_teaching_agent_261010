# 逐项教学反馈闭环候选

当前普通全章数学审阅可能把教学改进留为 warning 或不报告，从而在反馈已送达的情况下没有修订，也没有解释拒绝理由。候选为非空正式复检反馈增加独立逐项评估；已有数学 review/blocking 先走原修复循环，避免反馈失败冲掉已知数学问题。

原反馈全文与批准计划、实际正文一起保存。程序确定 F1/F2 等输入编号，模型必须逐项给出 satisfied、supported_improvement、rejected_not_supported、out_of_scope 或 unresolved。引文逐项本地验证。引用依据 unit_ids 与实际修改 repair_unit_ids 分开；只有后者产生原工作流可执行的 scoped review issue。反馈改善不冒充数学错误，不新增单元，不修改审批，原数学 issues 和累计全局轮次保留。

每个当前 job/plan/body/feedback/模型/检查契约对应一个持久评估槽，保存输入、原响应、失败、不可变回执及 SHA。有效未决或无效完整裁定在普通 retry 中持续阻断；没有完成响应的传输和预算失败才恢复同槽。BUDGET_EXHAUSTED 原样保留。该 role 不进行结构重抽，其他职责行为保持原样。所有正式任务写入检查 job lease。

feedback.reviewed 事件与证据文件一致，global_reports 收录完整回执，stage 为 teaching.feedback。API/UI 候选由另一清单提供当前动作绑定的回执展示。MockProvider 明确逐项表示离线演示不评估自然语言反馈；不会假称已落实建议。

验证分类：

- 隔离 mock 联合 **118 PASS，20.17 秒**：[日志](feedback-receipts-validation/20260920-181912-456058/pytest.log)、[JUnit](feedback-receipts-validation/20260920-181912-456058/pytest.xml)、[冻结上下文及 SHA](feedback-receipts-validation/20260920-181912-456058/context.json)。包含正式 TestClient 事件链、实际修改目标、warning 教学改进、数学先修、轮次保留、未决/无效阻断、传输/预算恢复、已保存响应、孤立响应、证据篡改、租约、诚实 mock 和新 role 单次结构响应。
- 早期扩展测试 **117 PASS / 1 FAIL** 保留在 [原日志](feedback-receipts-validation/20260920-181807-32f290/pytest.log)。失败为测试指定 schema repair=3 超过 Settings 合法上限 2；只改测试为合法 2，候选字节没有因此变动。
- 父任务执行的真实 API v1/v2 分别保存在 live-feedback-controls-20260920-1801 与 live-feedback-controls-v2-20260920-1808。本子任务没有调用 API。最终 helper 对 v2 原响应的[离线重验](feedback-assessment-final-saved-replay.json)：逐字证据及修改目标协议 2/2 PASS，严格本地分类匹配仍 **1/2**。第一题 F1 判应补独立夹逼练习，有具体依据；保留不同判断，不改预期、不抽第三次。该对照是同题针对性回归，不是盲测或权重训练。
- 本批没有执行 Windows XeLaTeX 编译、真实 Edge 或最终 PDF 全页视觉；由父任务部署后分别运行。教师数学/视觉验收均 **NOT_RUN**。不把 fake compiler 当 Windows 编译。

部署文件由 [feedback-assessment-manifest.json](feedback-assessment-manifest.json) 指定，candidate 路径相对本 reports/iteration4 目录。源文件生产 SHA 在联合测试前后未变。与 API/UI 清单合并共六文件。最终冻结须清单状态 READY_FOR_REVIEWED_DEPLOYMENT 且独审证据齐备；未冻结清单不可部署。

复现命令：

```powershell
.venv/Scripts/python.exe reports/iteration4/run_feedback_receipts_candidate.py --combined tests/test_feedback_assessment.py tests/test_feedback_assessment_pipeline.py tests/test_feedback_receipts_api.py tests/test_feedback_receipts_integration.py tests/test_recheck_feedback_pipeline.py tests/test_recheck_feedback_integration.py tests/test_teaching_quality_gate.py tests/test_global_budget_resume.py tests/test_provider_failure_artifacts.py tests/test_provider_prompt_identity.py
```

有界限制：编号提取只认顶层连续编号，任意未编号自然语言作为一个 F1 保留全文；引文匹配不能代替数学证明，模型对教学改进的合理性仍须实际内容与教师后续审核。真正越界请求没有对应单元时允许空单元依据，但必须引用实际批准范围。
