# CH03 round 3 后两次局部修订审计

**发现确定的跨单元证据误报，以及同一未改正文的 warning→review 漂移。不能把这两次接受补丁记成两项真实数学错误修复。** 本报告补充此前截至 round 3 修复前的审计，不改变其历史快照。完整输入、逐单元 diff、首次模型响应、补丁、SHA、真实 provider.result 对应及预算事件保存在 [JSON](CH03-S04-round3-local-followup.json)。

捕获时为 `GLOBAL_REVIEW / math.global_interfaces`、101 次请求；S04 局部状态 `CHECKED`。仍是 CH03 中间结果，未完成最终交付或教师验收。

| 动作 | 实际审阅与修改 | 只读核对结论 |
|---|---|---|
| round 3 全局修复 | 仅 S04.U03，把单侧无穷极限定义与双侧去心邻域条件分开。 | 真实处理一般定义范围；四种量词和原 `R\{0}` 上的 `1/x` 实例保留。 |
| local review 0 → repair 3 | Flash 将 S04.U05 标为 blocking，称末段只证要求 `g(x)≠b` 的复合极限；补丁仅改 U05。 | **确定误报。** 指称引文属于 S02.U03；目标 U05 从 round 1 前到 round 3 normalized 完全相同，原已证明复合连续性。补丁只是把邻域 `U`、`δ=min(δ₁,δ₂)` 显式写出，没有修复其声称的错误。 |
| local review 1 → repair 4 | Flash 将 U03 的双侧分类前提承接从 warning 升为 review；补丁仅改 U03，明确单侧定义独立、分类仍要求双侧域。 | U03 在这两次审阅之间完全未变。存在可澄清的读法，但 `(0,+∞)` 上的 `1/x` 不满足开头的双侧分类假设，不能证明该分类自相矛盾。补丁改善显式性，不是已确认数学矛盾修复。 |
| local review 2 | gpt6 仅保留 U04 与 U06 复合连续性重复的 warning。 | 没有再阻断前两项；现存真实 Windows 编译记录为 PASS。未进行本次独立重新编译或视觉验收。 |

误归属证据可直接定位：

- 首次响应：[local-0-review-0.json](../../workspace/iteration2-live/b/a45be503af594ce8/sS04_00aecb9ed051/local-0-review-0.json) 写出 `S04.U05：『最后证明复合极限结论。按该结论的假设……』`。
- 受检正确原稿：[candidate-normalized.json](../../workspace/iteration2-live/b/a45be503af594ce8/sS04_00aecb9ed051/candidate-normalized.json) 的 U05 已以 `f` 在 `g(x₀)` 连续、`g` 在 `x₀` 连续完成 ε–η–δ 证明；其 TeX SHA 为 `b096735f5c724baa924c48c56f408ca3538658b8e4cc1a7c493ba5bc0c9b868d`。
- 原文归属：[compile-attempt-2/source/lecture.tex](../../workspace/iteration2-live/b/a45be503af594ce8/sS04_00aecb9ed051/compile-attempt-2/source/lecture.tex) 第 208–212 行，所属 `% UNIT S02.U03` 标记在第 174 行。该处确实应证明复合极限，引用条件合法。
- 受检身份：`review-0.json` 的候选规范内容 hash 为 `f432f77a40c64e15c5ac4d756b1d0dabb42e5f2c5b531078e881a2b22d881d80`，本审计重算匹配。因此并非看到另一份新稿后猜测旧审阅错误。

首次和第二次审阅的实际模型均为 `deepseek-flash`，首选均为 `gpt6`（事件 1436 / 1453）；第三次实际为 `gpt-6-astra`（1466）。这些是既有真实调用记录，本审计没有调用 API。

预算应按实际单元计数说明：repair 3 把 U05 从 1 次提高到 2 次，旧每单元上限 2 **本身不会阻断这次**。repair 4 把 U03 从 2 次提高到 3 次，旧上限 2 会在此次提案前阻断；当前已获授权上限 6 允许继续。累计 `applied_rounds=4` 不等于任一单元已修 4 次；历史计数保留，未清零。更高预算避免过早停止，但也放大了错误证据造成无谓改稿的成本，应同时修复审阅归属校验。

建议工作流在存在正向跨单元引文命中时先进行一次定点证据核实：保存原始问题与引用来源，不凭“字符串没匹配”删除意见，不反复重新抽审至 PASS；须明确原问题是目标错误、合法依赖问题、误归属还是无法核实。无法可靠裁定时保持待处理状态并阻止内容补丁。对于范围澄清，必须继承前述假设，不能以不满足完整假设的端点例子称确定矛盾。

验证状态：审计脚本的身份、逐单元差异、引用归属和 provider 输出 hash 断言 **PASS**。新增 mock 测试、真实 API、Windows 编译均 **NOT_RUN**（本次只读）；读取到的既有真实 S04 编译为 **PASS**。最终全章语义、agent 全页视觉、教师数学与教师视觉均尚未验收，其中后两项明确 **NOT_RUN**。
