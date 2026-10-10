# 第二章正式反馈复检：正文改动跟踪

本报告是活动任务的中间追踪，**不是最终讲义验收**。任务 `fd6736af6ef14be3839e019e86ca1e5c`，正式复检 job `4678ed20f5c44ad89b289ffcee4d8143`；起点为 61 请求、17 页的反馈前稿。批准计划保持 revision 2。只读 SQLite/已保存模型产物，正文、数据库、原稿及生产源码没有由审计者修改；本审计新增 API 0，教师验收 NOT_RUN。

对应反馈：[CH02-agent-audit-feedback.txt](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/CH02-agent-audit-feedback.txt)。对照版本：[反馈前语义与全页报告](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/CH02-pre-feedback-semantic-visual.md)，PDF SHA `694d3b6783a984a65164ff3217fd19037c0333a25dac8603e70850b201115382`。

## 2026-09-20 17:44 UTC 快照：70 请求，S05 本地审阅

[只读快照](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/CH02-feedback-tracking/snapshot-20260920-174418-827461.json) 保存最新检查点、逐单元旧新正文、候选及恢复状态/SHA。S01–S04 为本轮新 CHECKED；S05 尚在强制重新检查阶段，不能把旧检查点当作本轮已完成。

|节|最新 checkpoint rowid|较反馈前正文变化|独立判断|
|---|---:|---|---|
|S01|37|无|保持原来正确内容|
|S02|41|仅 U10|模型语义误报触发的正确澄清改写，见下文|
|S03|42|无|极限比较应用反馈尚未落实，等待全章反馈审阅|
|S04|45|仅 U03|首指标/省略号表达显式化，新证明正确|
|S05|24（旧）|暂无|本轮尚未 CHECKED；U18 导航反馈不能宣布已解决|

### S02.U10：确定语义误报，不能计作数学纠错成功

原文：“假设相加后收敛，再减去原来收敛的级数，由定理 `thm:linearity` 将推出另一个级数也收敛，产生矛盾。”原 U08 定理允许对任意两条收敛实数项级数作任意实系数的线性组合。

取反证假设中的 `C=Σ(a_n+b_n)` 和原已收敛的 `A=Σa_n`。这两条级数此时都收敛；直接以系数 1、−1 应用已证线性定理，便得到 `Σb_n=C−A` 收敛，与题设矛盾。既没有对发散的级数和相减，也没有循环使用待证结论。原证明有效。

本轮 review-0 却说“反证假设只给出组合级数收敛，另一个原级数收敛，尚未满足该定理对两级数同时收敛的适用条件”。这里已经列出的两条收敛级数恰好满足前提，因此其“证明缺口”判断无依据。

模型 repair-5 将这一有效简证展开为 `B_n=C_n−A_n→C−A` 的有限部分和证明。新文同样正确，只改 U10，没有改变其他单元或原题答案；本轮后续 reviewer 与编译已接受。应记作 **不必要的数学修补/有效的教学澄清**，不回滚、不追加抽审，也不能在效果统计里写成“修复一项真实数学错误”。

证据目录：[sS02_2160fbbb764d](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/fd6736af6ef14be3/sS02_2160fbbb764d)。原始 review、修改前候选、patch、patch evidence、修改后候选和后续 review 已连同 SHA 嵌入快照。

这不是跨单元错引：引用确实来自当前目标，错误发生在审阅模型的数学推理。因此本轮窄归属 guard 不应伪称能解决它；应作为工作流剩余局限的真实证据。

### S04.U03：合理的首指标表达完善

原偶数部分和上界写为 `S_(2m)=b1−(b2−b3)−⋯−(b_(2m−2)−b_(2m−1))−b_(2m)≤b1`，讨论正整数 m。若把中间有限块在 m=1 时理解为空，证明路线成立；但显式末项指标 `2m−2` 在 m=1 时写成 0，未给空项约定时容易造成阅读歧义。

模型只补出 `m=1: S2=b1−b2≤b1`，再把原展开式限定 `m≥2`。这使最小指标明确，新证明保持原单调、有界、奇偶同极限路线，没有引入假设或删减证明。可记作 **边界表达完善**，不应声称发现了交错级数判别法错误，更不能与 S02 的推理误报合并为同一种“数学错误修复”。

证据目录：[sS04_ec8e066e11da](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/b/fd6736af6ef14be3/sS04_ec8e066e11da)。需要继续确认 S04.U07 的 m≥2、余项界、全部旧转义修复在最终正文和 PDF 中保持正常。

## 17:46–17:51 UTC：全部本地检查完成，真实反馈进入全章请求

[第二份只读快照](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/CH02-feedback-tracking/snapshot-20260920-174636-676046.json) 为 71 请求/GLOBAL_REVIEW。S05 已取得本轮 checkpoint rowid 46，正文无变化；五节候选与最新 CHECKED 检查点都相同。该快照额外冻结了 S04 原 review、patch 及新 review。

76 请求时进入 `teaching.chapter_coverage`。实际保存的 [chapter-coverage-912a485a-feedback.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/runs/fd6736af6ef14be3839e019e86ca1e5c/chapter-coverage-912a485a-feedback.json) SHA 为 `7715a6b0f4b534a60865a85614109b8289f1c2c7a598bc7232e265a6c6a31293`。已核对 source event 1527、job `4678ed20f5c44ad89b289ffcee4d8143`、plan revision/hash、`feedback_source=agent_audit`，以及 82 个单元 hash。模型实际得到的反馈文本与原反馈文件去首尾空白后逐字相同；这证明反馈已进入正式全章审阅请求，但此时尚不能宣称目标已修复。

四份相邻节审阅无 blocking/review。仅保留两个 warning：S03.U14 可补积分判别在 `[2,∞)` 上应用的说明；S04.U13 与 U07 余项证明重复。这与反馈前可选编排建议一致，不将 warning 冒称新的数学反例，也不据此触发额外无约束修订。

## 17:54 UTC：两项均被模型认可，导航却被降为 warning

首次全章反馈审阅 [chapter-coverage-912a485a-review-0.json](D:/研究生阶段/数学教学agent/math-teaching-agent/workspace/iteration2-live/runs/fd6736af6ef14be3839e019e86ca1e5c/chapter-coverage-912a485a-review-0.json) 明确报告两条反馈都有正文依据，但处理不同：

- S03.U14 极限比较应用训练列 `severity=review`，并明确“这不是现有直接比较解法错误”；78 请求时已进入 `repair.global.S03`。
- S05.U18 的确定导航矛盾列 `severity=warning`，虽然 message 写“应改为与全章题号回链一致的导航说明”，现有 global 修复只选 blocking/review，因此这一条尚未进入修复范围。

这是工作流中“模型已认可用户/agent 提出的有效改进，却被纯 severity 过滤漏掉”的实际证据，不能把识别问题等同于落实反馈。仍应等待 AUR 核实最终正文；审计者不会自行升 severity、再发 API 或手改 U18。新的逐项反馈回执协议应覆盖这种情形，不仅处理空 issues 漏项，也应让批准范围内的受支持改进独立于“数学错误”类别获得明确动作和最终核验。

## 17:58 UTC：正确新增应用，工具挡住错误核算 AST

80 请求时进入 `repair.section.S03`。全章修改已经给 U14(1) 增加完整且正确的极限比较应用：正整数 n 下两列为正，比值 `((3n+1)n²)/(n³+2)=(3+1/n)/(1+2/n³)→3∈(0,∞)`，参照 `Σ1/n²` 收敛，原直接比较解也保留。

但是模型新增核算 S03.C03 时，JSON AST 的 expression 只有 `Add(Mul(3,n),1)`，即 `3n+1`，并非正文的比值，却声明 expected=3。确定性 SymPy 返回 `oo` 并生成 SYMBOLIC_COUNTERCHECK_FAILED 是正确的阻断行为。当前 reviewer 也分清了正文与核算：正文极限正确，而工具失败尚未解决。

该处应由已有局部恢复修改核算表达式，使其对应真实正文；不能直接改 expected 为无穷后宣称已经验证比值，也不能把正确证明改成错误结论。此时候选为 `local-repair/S03/candidate-0c54e0f5d2f5.json`，未将尚未通过的候选当最终讲义。审计者没有修改 AST/正文或发起新模型请求。

18:03 UTC 的 [83 请求快照](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/CH02-feedback-tracking/snapshot-20260920-180310-209644.json) 已显示局部修复只更新 S03.C03：AST 为 `(3+1/n)*(1+2/n³)^(-1)`，expected 仍为 3，正确对应正文。patch evidence 的 `changed_unit_ids=[]`、`calculation_updates=[S03.C03]`，没有更改正确证明。恢复候选 SHA 为 `4f00ce3607532dceb7cc4b84e6baff4820cab4fa915cb5656cb2944e5f8f897c`。当时仍是 UNCHECKED_REPAIRED/LOCAL_REVIEW，不能仅因表达式改对就提前宣布编译或章节通过。

18:09 UTC 的 [89 请求快照](D:/研究生阶段/数学教学agent/math-teaching-agent/reports/iteration4/CH02-feedback-tracking/snapshot-20260920-180919-424642.json) 已保存核算修复后的 CHECKED 证据：S03 新 checkpoint rowid 47，产品实际 SymPy S03.C03 返回 3/PASS，该节 Windows 编译 PASS；S04/S05 也因依赖重查取得 rowid 48/49。五节与其当前候选一致。相较反馈前，正文仅改 S02.U10、S03.U14、S04.U03；S05.U18 仍逐字保留误导性导航，尚未落实第一条反馈。该快照同时保留错误 AST 原候选、正确 AST 新候选和只改计算的补丁证据。任务此时仍在 GLOBAL_REVIEW，并非最终 AUR。

## 最终审读待办

等待 root 通知 AWAITING_USER_REVIEW 并指定最终 artifact/SHA 后，再锁定产物，不提前对中间累计 PDF 作最终验收。逐条比对：U18 导航是否匹配全章答案顺序且实际回链仍正确；U14/U16 是否确实新增一个满足正项和有限正比值条件的极限比较应用；四个候选比值不能机械混用（U14(1) 为 3，其余已算三项为 1）。

最终须重核原稿全部 16 项与批准范围差异、原对数下限 2、奇偶指标/余项界、绝对收敛证明和 18 组题答链；对新 PDF 每一页实际查看，并重新解析 10 个答案回链。反馈前 17 页的视觉记录不能直接当成反馈后页数/内容的验收结果。模型审阅、实际 Windows 编译、agent 图像审读及教师验收继续分别记录。
