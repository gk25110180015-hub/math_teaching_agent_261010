# 缺失答案追加模块：离线回归完成，候选仍需后续审查

2026-09-20，本轮只实现 `answer_completion.py`、独立提示词和测试；未修改 pipeline 或 domain，未调用 API，未启动服务。

- [模块](D:/研究生阶段/数学教学agent/math-teaching-agent/src/math_agent/answer_completion.py) 提供 `missing_answer_targets(section)`、`propose_context(section, target_ids=None)`、`apply_answer_completion(section, reply, target_ids=None) -> (new_section, evidence)` 和 `AnswerCompletion` schema。
- [提示词](D:/研究生阶段/数学教学agent/math-teaching-agent/src/math_agent/prompts/repair_missing_answers.md) 只允许指定题目的答案正文、绑定新增答案 ID 的核算请求和追加说明；程序生成 `<target_id>.answer`、`kind=solution`、精确 `relates_to`。
- 原单元顺序、正文、已有答案、核算及任意原元数据均原样保留。未知/重复/已有答案目标、ID 冲突、超过 100 单元或 100 核算请求、外来核算绑定、伪造结果字段均阻断。不得重写或删除原题。
- 输出证据状态为 `APPLIED_UNCHECKED`，归一化、数学核算和教师审核明确 `NOT_RUN`。模块不宣称语义正确或审核通过；其结构范围检查不能替代后续内容审阅。

真实 CH02 初稿中 S02.U18/U19/U20 缺少显式答案。20 个原单元和 3 项原核算已复制为只读测试输入，原件与 fixture SHA256 均为 `fbe0234a6255d1dbb6d9a5aea13b907475df12024956309f831901516e14140b`；复制后及测试后重新核对一致。详见 [来源记录](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/answer_completion_fixture.json)。测试答案为人工编写的离线测试数据，未冒充真实模型响应。

| 验证类别 | 实际结果与证据 |
| --- | --- |
| 离线模块回归 | 最终 **58 PASS / 3.96 秒**，包括多目标顺序、已有答案和嵌套元数据保留、不可变输入、容量边界、冲突、错误关联、重复应用和非法结构。见 [测试](D:/研究生阶段/数学教学agent/math-teaching-agent/tests/test_answer_completion.py)、[最终日志](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/answer-completion-tests-02.log)、[JUnit XML](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/answer-completion-tests-02.xml)。 |
| 真实有界 SymPy 子进程 | 上述 58 项内实际运行两次原 `check_math`：新增答案的 `3×2−2×(−1)=8` 请求得到 `symbolic_check_passed`；非法 AST 未得到 PASS。这仅证明所请求表达式的核算和拒绝行为。 |
| 第一轮记录 | 55 PASS / 3.68 秒，[原日志保留](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/answer-completion-tests-01.log)。随后增加非法原 kind 类型及新理论环境边界覆盖，形成最终 58 项。 |
| 真实 API | **未执行**。最终命令及自动 fixture 显式将 `MATH_AGENT_LIVE_API_ENABLED=false`、`MATH_AGENT_API_KEY` 置空、`MATH_AGENT_LLM_STREAMING=false`；未导入 Windows User 环境。 |
| Windows 编译 | 本模块轮次 **未执行** XeLaTeX；Windows 上运行 pytest/SymPy 不等于编译验收。集成编译由 root 的独立测试记录覆盖。 |
| 人工教师视觉/数学验收 | **未执行**。 |

最终运行命令（在项目目录，三个模型环境变量已如上设置）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_answer_completion.py -q --basetemp workspace/t/ac02 --junitxml reports/iteration2/answer-completion-tests-02.xml
```

pipeline 集成仍须保留不可变候选及缓存身份、重新规范化正文、运行原有内容/引用/安全/核算/模型审阅与实际编译。此模块只追加未审核答案，不承担批准计划或发布产物的职责。

## 独立集成复核

随后只读审查 root 新增的 `answer_recovery.py` 与 pipeline 缺失答案分支，并独立执行现有 `tests/test_answer_recovery_pipeline.py`：**3 PASS / 11.75 秒**，见 [日志](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/answer-recovery-independent-01.log) 和 [JUnit XML](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/answer-recovery-independent-01.xml)。三项均使用测试提供者，真实 API 未执行。

- 1 项实际 Windows XeLaTeX：新增答案置于讲义末尾并有编号链接，原题及计划审批保留，未产生人工审核记录。
- 2 项 mock 编译集成：审阅中断后复用未审核答案提案并重新审查；新增错误核算即使测试审阅器无异议也仍被阻断。
- 独立目录 `workspace/t/acp1` 保留测试 PDF、源码、日志和失败/恢复状态，无服务启动。

审查指出 context 构造阶段的确定性容量/ID 错误原本会成为普通 FAILED；root 随后补充 `ANSWER_COMPLETION_BLOCKED` 及模型调用前诊断。此修正需要 root 的单独定向测试，本段的原有 3 项不覆盖该新分支。除此以外，本轮只读审查未发现阻止当前集成的其它具体问题。无教师视觉验收、无形式化证明。
