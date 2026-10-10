# 已准备的数学声明疑点恢复候选

此候选对应已批准的窄方案 A。生产源码、原稿、生成讲义、真实任务 DB 未修改；没有创建新草稿发布通道，没有改通用 MathReview、WrittenSection 或 LocalPatch。

实现实际 ID 前缀正向定位、保留原 uncertainties 的完整原文和哈希、准确移除 Pipeline 重复注入，以及每条疑点的显式裁定。`resolved_by_current_body` 必须有实际正文逐字证据；`open_actionable` 进入原有限定单元修复；`open_dependency` 保存明确阻断，不能凭条件性声明假装证明完成。普通 MathReview 的独立问题和工具 UNKNOWN 不受消解操作影响。

专用角色为 `reviewer_uncertainty`，响应 schema 为 `UncertaintyAssessment`。只允许一次完整 schema 响应；传输故障仍由既有 gpt6→Flash→Pro 路由处理。已完成的无效或未决裁定不因普通 retry、新 job 或模型偏好变动而重抽。纯传输失败可以在同一冻结输入槽位恢复；预算耗尽原样上抛，旧计数与审批不重置。

普通数学审阅在新裁定调用之前单独持久化。即使裁定超时，恢复也不能先重抽 ordinary review 到空 PASS 再丢旧阻断。恢复还覆盖“失败证据已登记，但 INVALID/TRANSPORT_PENDING 状态尚未保存就崩溃”的边界。未知同 rule_id 的问题不被视作声明；遗留重复只在候选/原 review identity/原工具报告及实际文本均支持时映射，并保留原文件。

候选文件及精确 SHA 由 `uncertainty-review-manifest.json` 给出。`uncertainty-pipeline.patch` 只涉及 check contract 和 `_lecture_sections` 的局部审阅，可叠加到 global LocalPatch 候选，不覆盖其修改。`build_uncertainty_candidates.py --pipeline-base <全局候选路径>` 可生成叠加版本；应把该模块的 REPORTS 设为独立输出目录，避免覆盖本次已经测试的候选历史。

最终专项：`uncertainty-validation/20260920-192956-044419/`，**153 PASS，20.12 秒**。其中 44 项是新增疑点测试，另有现有局部恢复、严格 LocalPatch、numeric/UNKNOWN、反馈闭环和供应商传输回归。真实 SQLite 与本地数学检查按实际执行；模型和编译器均注入 mock。真实 API、Windows XeLaTeX、浏览器和教师数学/视觉验收均 **NOT_RUN**。生产 SHA 前后相同。

交付清单另包含 `tests/test_uncertainty_review.py` 和 `tests/fixtures/uncertainty_ch03/` 两份冻结样本原字节。测试只把 fixture 路径改为 tests 下目录后，从隔离包实际交付位置再次运行 **44 PASS，3.68 秒**，证据 `uncertainty-validation/20260920-193337-2c7e54/`。四个生产候选字节未变化；两原样本 SHA 保持 `7adce019…` 和 `5fe32ace…`。最终独审报告为 `uncertainty-review-independent-audit.md`。

复现命令（工程目录内）：

```powershell
.venv/Scripts/python.exe reports/iteration4/run_uncertainty_candidate.py reports/iteration4/test_uncertainty_review_candidate.py tests/test_local_recovery.py tests/test_local_patch.py tests/test_numeric_evidence_classification.py tests/test_feedback_assessment_pipeline.py tests/test_provider_transport_recovery.py
```

保留的历史验证包括：`192406-63d3b0` 测试文件命名导致收集失败、`192431-64afff` 38 PASS/1 测试对只读属性赋值失败、`192533-e54aaa` 125 PASS、`192711-b68382` 150 PASS。这些不替代最终版本的 153 项证据，测试预期没有为数学结果改写。

新增事件 `math.uncertainty_reviewed` 包含 job/origin_job、批准 plan 身份、identity、status、ledger 路径和 SHA，teacher_review 始终 NOT_RUN。ledger 保存 input、ordinary-context、ordinary-review、assessment-input、response、assessment/failure 与依赖哈希。若进程恰好在最终 ledger 提交后、事件发出前崩溃，完成裁定仍能由 ledger 和局部报告恢复，事件本身不保证已发出；不能把事件缺失当没有裁定后重抽。此版本没有扩大事件投递架构。

本案的数学状态没有被此候选自动改变：S03.U04 正弦估计已实际补正；指数不等式的精确依据仍需实际正文/材料支持。独立 Euler 证明分析 note 不是已批准来源，也没有被自动放进模型输入、正文或来源目录。存在现有范围内可补的非循环初等证明时，可按 `open_actionable` 提议；尚未实际写入并审阅前不能宣称已完成。
