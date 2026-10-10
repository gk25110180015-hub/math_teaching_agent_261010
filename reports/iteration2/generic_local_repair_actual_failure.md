# CH01 S04 实际越界修复：继续拒绝第二轮候选

**本次 `REPAIR_SCOPE_VIOLATION` 是正确阻断。第二轮只授权修改 S04.U04，模型却同时改写 S04.U03；规范化未改变任何单元，不能以归一化差异为由放行，也不能偷偷恢复 U03 后接受其余响应。**

实际目录：`workspace/iteration2-live/b/05748ab6260c4098/sS04_275ca369f149/`。哈希、完整前后单元、问题原文和只读数据库快照见 [JSON 证据](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/generic_local_repair_actual_failure.json)。本轮没有修改候选、运行状态或产品代码，没有调用 API、重试任务或运行测试。

`review-1.json` 仅对 S04.U04 给出 review：证明已明确使用上确界/下确界性质，但需核对批准的课程背景是否允许实数完备性作为外部已知前提。第二轮响应实际改动：

| 单元 | 实际变化 | 判断 |
| --- | --- | --- |
| S04.U03（非目标 theorem） | 递减分句由“若 $\\{a_n\\}$ 单调递减且有下界”改为“若实数数列 $\\{a_n\\}$ 单调递减且有下界”；新增“实数数列”四字 | 未经授权正文变化，必须拒绝，即使措辞看似冗余 |
| S04.U04（授权 proof） | 将基础性质说明改为明确的“外部已知”，并强调证明以课程允许这两条性质为条件；后续推导不变 | 属于授权位置的修改，但这种自述本身不能证明课程确实允许该外部前提 |

`repair-2-normalization.json` 的 `raw_hash` 与 `normalized_hash` 都是 `9370c074f90854be337ddc7c3f429e1dc308959603472d3644e20b83d80636d1`，与实际 raw section 的规范 JSON 哈希一致；全部单元 `action=unchanged`。ID/顺序及 section 其余字段没有变化。失败来自模型对 U03 的正文改写，不是规范化误报。

数据库实际记录：run `05748ab6260c40989a560a98e1e2065a` 为 `BLOCKED / repair.section.S04`，请求累计 26，错误于 `2026-09-19T19:17:13.219921+00:00` 保存，code 为 `REPAIR_SCOPE_VIOLATION`。S01/S02/S03 有 checkpoint，S04 没有。因此先前审查所指的“修后候选未 checkpoint 就失败”条件已实际发生；**本轮未执行 retry，尚不能宣称已经观察到重试丢弃改进或发生重复收费**。

可供最小安全局部恢复使用的实际证据已经齐全：

1. `draft-reuse.json` 保留 writer context/model/provider/prompt/schema 身份和原候选路径/哈希；`candidate-normalized.json` 是第一轮修复 before 的可验证起点。恢复还须核对当前批准 plan 与 S01–S03 checkpoint 身份一致。
2. `review-0.json` 的修复目标恰为 U04/U06；`repair-1.json` 实际也仅改变这两项，单元顺序与其余 section 字段保留，before/after 哈希链正确，第一轮规范化 PASS。它可以成为 **UNCHECKED_REPAIRED** 恢复种子，不能冒充已审核 checkpoint。
3. `review-1.json` 的 U04 外部前提问题必须随该种子保留。先由实际批准计划/课程约束证据处理这一问题；单纯重发 reviewer 直到不报疑点不能算解决。
4. 第二轮 raw/normalization/错误记录保持隔离，只作为被拒绝的证据；不能从中择取 U04、回填 U03或抹平差异后自动放行。
5. 修复轮次记账必须包含已付费但被拒绝的第二次调用；当前尝试已发起两轮，不能只因最后有效种子是 repair-1 就声称仅消耗一轮。剩余 API/局部修复预算须显式核对，不通过 retry 自动归零。

如 root 决定实施恢复，最小新增仅是经上述身份/哈希/授权链核验的未审核候选指针及问题/预算状态；恢复后仍运行完整规范化、引用/安全/核算/审阅与编译。无需放宽现有非目标内容保护，也无需重新生成前三节。批准计划对实数完备性的具体许可由 root 另行核查，本报告不推断“允许”或“禁止”。
