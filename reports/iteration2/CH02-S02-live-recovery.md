# CH02 · S02 真实恢复链只读核验

结论：**S02 已保存的答案恢复、严格局部补丁和小节检查证据核验通过**。64 项证据断言通过，30 个来源文件在审计期间 SHA-256 一致；这不是整章通过或教师审核。最终只读数据库快照显示任务已在后续 `write.section.S03` 失败，累计 19 次请求，计划版本仍为 2。

运行：`fd6736af6ef14be3839e019e86ca1e5c`。完整逐项断言、文件 SHA、请求与局部状态事件、编译/核算记录见 [CH02-S02-live-recovery.json](CH02-S02-live-recovery.json)。[审计脚本](audit_CH02_S02_live_recovery.py) 仅用 SQLite `mode=ro` 读取事务及文件读取；只在内存重放确定性补丁并比较数据。本审计 **未调用模型、未重编译、未改数据库、未启动服务、未提交教师审核**。

## 实际候选链

1. 旧目录 [sS02_a3c5b831b6c6](../../workspace/iteration2-live/b/fd6736af6ef14be3/sS02_a3c5b831b6c6/) 的 `repair-1.json.section`，与新答案恢复提案的 `before.json` **整个对象完全相等**。旧 U18、U19、U20 中已经接受的内嵌“答案：”保留为恢复基线，没有退回原作者初稿。旧 `repair-2-raw.json` 继续标记 `REJECTED_NOT_ADOPTED`，没有作为恢复种子。
2. 新 `repair_missing_answers` 提案先完整保留原 20 个单元、原顺序及 3 条计算，再新增 `S02.U18.answer`、`S02.U19.answer`、`S02.U20.answer`，三者都是 `solution` 并分别精确 `relates_to` 原练习。新增的 `S02.AC01` 只绑定 `S02.U18.answer`，核算第一个级数通项极限 `2/3`。这一阶段没有隐式删改题干里的内嵌答案。
3. 复核仍对 U18—U20 报告答案位置阻塞。随后真实 `repair_local_patch` 只返回三项 `unit_id → tex` 替换；无计算更新、无计算新增。对每题直接比较发现：最终正文恰等于旧已接受正文中 `\n\n答案：` 之前的完整前缀，题目本身未重写。
4. 严格补丁保留全部 23 个单元的 ID、kind、relates_to、顺序及其他 metadata，保留非目标 20 个单元（17 个原单元及 3 个新增答案）整个对象不变；原 3 条计算及新增 AC01 均逐字保留。已有 uncertainties 与 calculation_limitations 保留。
5. 最终持久候选与 `repair-4.json.section`、数据库 `section.S02` 检查点中的 generated 完全相等。旧来源依赖哈希、提案输出哈希、检查点哈希均核验一致。

主要语义哈希：

| 节点 | SHA-256 |
|---|---|
| 旧已接受稿 / 新补答案 before | `db46e9427174364b657889cb04f2ccd9748fdd0c72e357472020c259892ebaa4` |
| 新增独立答案后 | `ae68f99d5dcbf8c2cebefe48f8a735d8b7b484fbec86698dfd149f57677e000c` |
| 严格补丁后的最终小节 | `118ed3ed4fd67fc595963483bd8ba6f1a65c8e87ae5ab12007f9b246a124a071` |
| 数据库小节检查点 | `2af2bc64cd5bb2e928c25d521f62f94ffc0d4656e64acec1b2735a13f111a43c` |

这里的语义哈希按项目 canonical JSON 计算；JSON 文件的原始字节 SHA 单独保存在结构化审计中，两者没有混用。

## 请求、修复次数与真实接口事件

旧链导入时已有 11 次请求、1 次已接受修复、2 次提案、1 次拒绝，均保留。S02 本轮再发出以下 5 次真实请求，完成小节时总请求为 **16**；第 17 次及之后请求属于后续 S03，不计作 S02。

| 运行累计请求序号 | role | prompt_version | provider.request 事件 | 结果 |
|---|---|---:|---:|---|
| 12 | reviewer_math | 3 | 560 | HTTP 200，完整 SSE，schema attempt 1 通过 |
| 13 | repair_missing_answers | 1 | 567 | HTTP 200，完整 SSE，schema attempt 1 通过 |
| 14 | reviewer_math | 3 | 574 | HTTP 200，完整 SSE，schema attempt 1 通过 |
| 15 | repair_local_patch | 1 | 581 | HTTP 200，完整 SSE，schema attempt 1 通过 |
| 16 | reviewer_math | 3 | 587 | HTTP 200，完整 SSE，schema attempt 1 通过 |

五次事件都记录真实 `prompt_hash`、`schema_hash`、`prompt_version_source=declared_prompt_header`。审计将这些哈希与实际对应提示文件/schema 比较，并将 schema 成功事件的 output_hash 与保存的提案/复核 JSON 比较，全部匹配。补答案 schema hash 为 `33f1dd4a1048269d000f52f3663cc9fdac32afe07edfda814a6c018869562c33`，严格补丁为 `0d86c8d71317f64b5b07f16f49a50ad4dd13c072cbf83dcaa1babdd53d1510dd`。更早旧 reviewer 的 prompt hash 仍为 `UNKNOWN_NOT_ARCHIVED`，没有倒填。

最终 [S02 持久状态](../../workspace/iteration2-live/runs/fd6736af6ef14be3839e019e86ca1e5c/local-repair/S02.json) 为 `CHECKED`、pending_issues 空，计数如下：

- `applied_rounds=3`：旧接受修复 + 补关联答案 + 严格局部补丁。
- `proposal_calls=4`、`rejected_proposals=1`：包括旧链的两次提案与一次拒绝。
- U18/U19/U20 每单元累计接受修改 2 次；三个新 `.answer` 单元各 1 次。
- 每个原题的 `unit:*` 提案累计 3 次、拒绝 1 次；对应 `answer:*` 提案各 1 次。
- 请求预算仍为经证据迁移的 **60**，预算 version 0、overrides 空、budget_actions 0。原批准计划 hash 与局部状态身份一致，没有增额、重置或重新批准。

## 已执行检查与保留限制

已保存的小节检查点记录：3 项原有符号计算 C01/C02/C03 与新增 AC01 均为 **SymPy PASS**，最终 local reviewer issues 为空，references PASS。实际 Windows `D:\texlive\2024\bin\windows\xelatex.exe` 双遍编译 **PASS**，耗时 3.734 秒、6 页；两遍日志、源文件 SHA 和实际 PDF 字节 SHA 均核验。见 [compile.json](../../workspace/iteration2-live/b/fd6736af6ef14be3/sS02_535f6e66022e/compile.json) 与 [局部 PDF](../../workspace/iteration2-live/b/fd6736af6ef14be3/sS02_535f6e66022e/build/lecture.pdf)。该 PDF 是累计 S01+S02 草稿，不是最终整章。

答案和补丁提案自身的审计仍写 `APPLIED_UNCHECKED / math_check=NOT_RUN`，这是提案应用阶段的事实；其后的数学复核与实际编译通过在独立小节检查点记录中，不能把前者标签改写成全流程验收。

早两轮 reviewer 对未修改的 U14 还给出 warning 级观察，最终模型复核没有重复这些警告。U14 确实保持未动，警告原文留在结构化报告的 review_issue_progression 中；本审计不将模型重新判断视为教师裁定或形式化证明。工具只覆盖显式的 4 个符号核算请求；未进行教师数学、视觉审核，未重渲染或查看最终整章排版。

审计脚本首轮因误用审批列名 `plan_hash` 而停止，仅修正为实际列 `hash` 后重跑；未触碰产品或任务数据。[首轮脚本日志](CH02-S02-audit-attempt-01.log) 与 [成功日志](CH02-S02-audit-attempt-02.log) 均保留。后续 S03 的失败与整章后续检查由主流程继续处理，不在本小节核验中宣称通过。
