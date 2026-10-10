# Generic local repair 恢复只读审查

结论：**若普通局部修复后的审阅/编译在 section checkpoint 保存之前失败，当前重试会回到原 writer 草稿，修复产物虽仍在磁盘，但不会作为重试起点。当前指定的 CH01 S02 没有触发这种失败：两次修复后审阅和编译已通过，完整修后候选已经进入 checkpoint，不建议为这一已通过节新增恢复机制或重启任务。**

## 实际证据

本轮只读读取文件及 SQLite `mode=ro`，未调用 API、未注入故障、未运行测试或启动服务。观察时间、文件哈希及数据库快照见 [JSON 证据](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration2/generic_local_repair_review.json)。

指定目录 `workspace/iteration2-live/b/05748ab6260c4098/sS02_d764aedf5652/` 内：

- `repair-1.json` 相对原稿仅改变 `S02.U11`；`repair-2.json` 相对 repair-1 仅改变 `S02.U09`。两轮 before/after 哈希链均与实际 section 一致。
- `review-2.json` 的 math 为 PASS，仅余 warning，blocking/review 项为 0；`compile.json` 为 PASS。
- 数据库 `section.S02` checkpoint 创建于 `2026-09-19T19:07:18.473650+00:00`；输出哈希有效，`generated` 与 repair-2 完全相等，源码文件哈希有效。
- 观察时任务为 `BUILDING / write.section.S03`，并无 S02 修复后的失败。writer-cache 仍指本目录原 `candidate.json` 且哈希有效，这与已存在的修后 checkpoint 并不冲突。

因此，后续节失败且计划/先前章节身份未改变时，S02 会优先命中已通过 checkpoint。不能把“writer-cache 仍是初稿”单独当作本次已经丢失修复或重复付费的证据。

## 代码可达的恢复缺口

[writer_draft](D:/研究生阶段/数学教学agent/math-teaching-agent/src/math_agent/pipeline.py:190) 只接受缓存指向的 `candidate.json`，身份匹配且字节哈希通过后复制到新 attempt；并未查找 `repair-N.json`。

[_lecture_sections](D:/研究生阶段/数学教学agent/math-teaching-agent/src/math_agent/pipeline.py:510) 优先使用已通过的 section checkpoint，否则取得 writer 草稿。普通局部修复在约第 598–607 行保存 raw、normalization 和 `repair-N.json`；此处没有更新可恢复候选指针。section checkpoint 到约第 621 行、审阅及编译门禁之后才保存。因此存在以下静态可达路径：

1. 普通修复已生成且通过范围校验；后续 reviewer 超时/失败、预算耗尽后仍有疑点，或局部编译阻断；此时尚无本节 checkpoint。
2. 重试调用 writer_draft，复用原初稿而不是最后一份修后候选；审阅/修复调用可能再次发生。局部 `attempt` 循环也从 0 开始，虽然总 API 请求预算仍约束收费上限。
3. 原 repair 文件没有被删除，问题是它们没有被安全选为恢复起点。不能描述为原修复证据被覆盖或丢失。

全局修复有独立持久化 state：[_continue_global_repairs](D:/研究生阶段/数学教学agent/math-teaching-agent/src/math_agent/pipeline.py:430) 在重新审查前保存候选指针；但若重新审查过程中又发生普通局部修复，并在 `on_rechecked` 回写前失败，这些额外普通修复同样不在全局 state 内。标签/补答案专用恢复缓存也不自动覆盖 generic repair。

## 现有测试能证明的范围

[test_draft_recovery.py](D:/研究生阶段/数学教学agent/math-teaching-agent/tests/test_draft_recovery.py:56) 覆盖原 writer 候选在 reviewer 超时后的未审核复用、身份失效及重新检查；测试提供者没有执行普通 `repair_content_unit`，因此不能证明普通修后候选被恢复。

[test_global_repair.py](D:/研究生阶段/数学教学agent/math-teaching-agent/tests/test_global_repair.py:192) 覆盖全局修复持久化后，后续节 reviewer 超时再恢复，以及缓存篡改阻断；不覆盖 generic local repair 之后、section checkpoint 之前的失败。本轮仅阅读测试，**未重跑，不新增 PASS 声明**。

## 仅在真实后续失败需要时的最小安全设计

保持原 writer 草稿和已通过 checkpoint 的职责不变，增加一个本节“未审核修后候选”指针即可，不扫描目录按文件时间挑所谓最新稿，也不将 repair 直接冒充已通过 checkpoint。

- 身份绑定计划哈希、section spec、原 writer 候选/上下文及前序已完成章节哈希、模型/provider、repair prompt/schema/normalizer 版本；原稿、raw、规范化记录、before/after 哈希链和问题记录均不可变保留。
- 在规范化及范围校验之后、下一次 reviewer/compile 之前，以当前 job fence 原子保存 `UNCHECKED_REPAIRED` 指针、实际候选字节哈希、已用修复轮次和未解决问题。路径限定在当前 run 的受控目录；哈希/结构/身份不符应明确阻断，不能静默选择其它稿件或付费重写。
- 恢复后重新运行规范化、引用/安全/内容检查、原有核算器、模型审阅及编译；不复用旧 PASS。网络中断可重新检查同一候选；已确定的 blocking/review 疑点不能仅靠反复抽取 reviewer 抹去。已用轮次不能在 retry 时清零，预算耗尽必须保留阻断。
- 安全导入需核对 section ID、完整单元 ID/顺序、非目标单元正文/metadata、非目标核算和无关疑点。现有 generic guard 只比较 ID 集合和非目标 unit 字典；恢复机制不应把它当成顺序及全部 section metadata 已受保护的证据。
- 如要导入旧 `repair-N.json`，只接受能与原稿和每轮已保存问题形成完整哈希/授权目标链的候选；无法证明就保留并要求人工处理，不能按 mtime 猜测。

届时只需补有界离线用例：修后 reviewer 超时再恢复、修后编译失败再恢复、两轮改进均保留且不重发 repair、预算耗尽不重置、候选篡改/前序变化拒绝复用。当前 CH01 S02 已有安全 checkpoint，**本轮不实施补丁、不更改运行中的产品快照**。教师视觉/数学验收未执行。
