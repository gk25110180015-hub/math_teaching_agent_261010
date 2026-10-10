# 数值抽查证据分类修复验收

只修改 `mathcheck.py` 成功数值抽查分支：`NUMERIC_IS_NOT_PROOF` 从 `review` 改为 `warning`。工具仍明确记录“不是一般性证明”，数学总状态仍为 `NEEDS_REVIEW`，证据类型仍为 `numeric_spotcheck_passed`。没有改变数学表达式、核算结果、审阅模型阻塞或预算策略。

这解决了 CH02 S04 的一项实际产品缺陷：U05 已明确数值演示范围，U06 独立给出一般性推理，但工具局限仍被反复当成 U05 正文错误，导致两次无变化提案。完整只读审计见 `CH02-S04-budget-audit.md/json`。原任务仍为 `BLOCKED`，请求数仍为 33；U07–U13 的真实 TeX 转义错误未解决。

先红后绿证据：

- 初版红测试：4 失败、4 通过；其中 1 个测试错误地要求已定义的单点 `n=3` 返回定义域 UNKNOWN。已改为“所有实数上 n/n=1”的真实缺定义域声明，原日志保留为 `numeric-classification-before.log/xml`。
- 修正后的红测试：**3 失败、5 通过**，见 `numeric-classification-before-corrected.log/xml`。三个失败分别重现错误严重性、强制发起无必要补丁、旧疑点无法退出修复目标。
- 修复后：**55 通过、0 失败、0 跳过，54.15 秒**，见 `numeric-classification-after.log/xml`。包括新增 8 项及原数学检查、核算协议、局部恢复、草稿恢复测试。

新增回归使用捕获的真实 U05/U06/C01 只读副本和真实 SymPy 子进程，验证：成功单点证据仍非符号证明；数值反例仍 FAIL/blocking；UNKNOWN、定义域和声明疑点仍为 review；有独立论证的演示不发起正文补丁、不耗单元次数；mock 审阅指出“把抽查当一般证明”仍能阻塞。历史恢复测试保留全部旧审核文件及 SHA、3 次提案和 1 次实际修改计数，新的工具结果可供重新评估，预算本身不放宽，再请求同单元补丁仍会耗尽阻塞。

测试类型严格区分：

| 类型 | 本次结果 |
|---|---|
| MOCK API/工作流 | PASS，注入 fake provider，独立 SQLite 与 fake compiler |
| 真实 SymPy 核算 | PASS，受限环境子进程实际执行 |
| Windows XeLaTeX | PASS，原局部恢复回归中 1 项实际编译，两轮、实际 PDF/SHA；不是 CH02 S04 编译 |
| 此修复的真实 API 验证 | NOT_RUN，没有发送请求 |
| 教师人工视觉/教学验收 | NOT_RUN |

实际 Windows 产物位于 `workspace/t/nmaf93/test_strict_local_patch_is_rec0/w/b/59869f250761478e/sS01_ec8716a37ffc/`。编译证据和冻结后的三个文件 SHA 见同名 JSON。测试显式使用空 API key、live=false、streaming=false；没有导入 Windows User API 配置。

测试结束后重新只读核对原失败的全部 21 份证据，SHA 全部一致；原数据库仍为 `BLOCKED / review.section.S04 / request_count=33`。原审批、请求/修复计数及预算没有改写。现有 UI 的显式预算恢复流程也未绕过，后续由用户和根任务按实际门禁处理。
