# 引文归属门禁候选与验证

真实 CH03 审阅曾把 S02.U03 的复合极限证明错归 S04.U05，导致正确的连续性证明被再次修订。候选在正文修复前核对这类可明确定位的长直接引文，并要求一次逐条、有实际目标反证或真实依赖证据的裁定。原始问题、模型响应和核实证据完整保存。工作流仍使用原批准计划、现有 global/local 修复和累计预算；不直接编辑已交付稿。

可部署文件与原生产 SHA 见 [manifest](review-evidence-attribution-manifest.json)。其中 pipeline 已合并此前 feedback 候选；新 schema 位于独立 helper，不覆盖 API/UI 的 RecheckRequest。新 helper、裁定 schema、提示词均纳入 section check contract；全局 patch 契约和已用 rounds 不变。提示词版本为 1，已有 reviewer_math V6 未修改。

只有明确归属目标的引文在目标缺失、在另一个实际已提供单元唯一命中时才触发；缺定义等无引文意见照常处理。合法跨单元依赖批评可以通过证据核实保留阻断，不自动删除或转移到其他单元。纯空 issues、缺目标反证、错引文、越界 ID 或 unresolved 都不能解除原疑点。未涉疑的原问题保持原样。

恢复状态绑定实际正文与上下文、批准计划、当前 job、模型和检查契约。相同 job 的 retry 不重新抽取普通审阅；有有效未决或无法定位的裁定时保持 `REVIEW_EVIDENCE_BLOCKED`。三路 API 均失败且没有完成响应时保存 `TRANSPORT_PENDING`，正式 retry 继续同一个已保存核实输入；请求耗尽保留 `BUDGET_EXHAUSTED`，需原显式增额流程。已落盘响应优先验证，未登记的孤立响应阻塞。正式 recheck 新建 job，仍会执行新全章审阅，不跨 job 套用旧全部结论。所有证据写入遵守当前 worker lease。

部署前验证分开记录：

- 新定位、裁定和恢复回归与既有反馈/API、全局历史、cache 测试均在隔离 src 包运行；最终 **74 PASS / 18.33 秒**，证据 [pytest.log](review-evidence-guard-tests-138950/pytest.log) 和 [JUnit](review-evidence-guard-tests-138950/junit.xml)。其中 32 项新回归、42 项既有回归，均为 mock；首轮 69 PASS、次轮 73 PASS 仅代表相应历史候选，不冒充最终版本。
- 2 个真实 API 定点对照由根任务独立执行：保存的错引撤销且保留 U03 warning；真正分母为零的依赖错误继续 blocking。两次均实际 gpt6、HTTP 200，详见 [真实对照报告](REVIEW_ATTRIBUTION_LIVE_CONTROLS.md)。API 时冻结 helper 与最终恢复/错误码版本不同；最终 helper 对这两个保存响应离线重验，记录 [saved replay](review-attribution-final-helper-saved-replay.json)，未重复已完成裁定。
- 本候选未运行新的 Windows 编译、最终 PDF agent 视觉、教师数学或教师视觉验收；这些均 **NOT_RUN**。部署后全回归和 Edge 验收由根任务单独记录。

新测试：`tests/test_review_evidence_attribution_candidate.py`、`tests/test_review_evidence_guard.py`。隔离回归入口：`.venv/Scripts/python.exe reports/iteration4/verify_review_guard_candidate.py`。已保存真实响应离线复核入口：`.venv/Scripts/python.exe reports/iteration4/verify_final_attribution_saved_responses.py`。`prepare_review_guard_candidate.py` 是生成器；最终 READY manifest 冻结后不可重新执行以免覆盖部署状态。

限制：这是针对正向可定位错引的窄门禁，不覆盖所有模糊转述、没有直接引文的数学幻觉或严重度漂移。逐字位置可由程序验证，但裁定的数学含义仍依赖模型核对，不等于形式化证明或教师验收。已知案例及同题提示词调整属于针对性回归，不是盲测或模型权重训练。
