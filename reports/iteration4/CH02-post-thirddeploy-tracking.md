# 第二章第三部署后真实恢复跟踪

只读审计：不调用 API、不重试任务、不修改生产、数据库或正文。任务 `fd6736af6ef14be3839e019e86ca1e5c`，恢复原 job `4678ed20f5c44ad89b289ffcee4d8143`，累计从 101 请求继续。最终审计等待父任务锁定 artifact/SHA；本报告不以中间累计稿宣称最终通过，教师数学/视觉验收均 NOT_RUN。

## 105 请求：正文未变，新契约重新检查

快照 `CH02-post-thirddeploy-tracking/snapshot-20260920-184117-692031.json`：S01、S02 取得新 CHECKED rowid 52/53；五节所有当前单元仍与第三部署前 101 请求基线相同。S03 正在按新检查契约重审，状态 UNCHECKED_FORCED。此前 gpt6 HTTP 504 后工作流实际切换 deepseek-flash；Flash 于 145.219 秒后收到完整 HTTP 200 正文。仅收到响应头时未提前记作审阅成功。

## 106–109 请求：S03.U12 发生范围解释往返

证据目录 `workspace/iteration2-live/b/fd6736af6ef14be3/sS03_c4b8f8d619f6/`：`local-0-review-0.json`、`repair-5-patch.json`、`local-1-review-0.json`、`repair-6-patch.json`。109 请求快照为 `CH02-post-thirddeploy-tracking/snapshot-20260920-184451-822106.json`，保存最新候选、保留问题、工具检查、原有计数及 SHA。

1. Flash 的 local-0 并未指出原积分判别证明错误，反而明确承认其完整证明了两个方向；它认为该证明与批准排除项“不系统展开高等数学中的积分判别法证明细节”可能冲突，又注意到 proof_policy=key 要求完整关键证明。
2. repair-5 只改 S03.U12，把原正确完整证明缩成相邻矩形积分估计和使用条件说明，明确“不展开两方向的完整证明”。没有改任何计算请求或 U14。
3. gpt6 的 local-1 随即根据关键定理/reference_labels 和 proof_policy=key，指出缩短稿没有双向证明，仍要求解决范围适用边界。
4. repair-6 仍只改 S03.U12，恢复矩形估计到部分和有界的双向论证，并用整数端点积分序列与夹逼明确实上限极限；首句说明只用基本积分估计和单调有界，不展开反常积分一般理论。该证明数学上正确，是否被后续模型接受尚需等待。109 请求时为 UNCHECKED_REPAIRED，不能提前声称 CHECKED。

独立判定：这不是两项真实数学错误，更不是正确比值 3 被改错；是批准范围解释冲突导致先删后补。原稿中单调有界的截断积分论证本来有效，新稿整数端点夹逼是有效展开。没有依据回滚正确新稿或重新抽样求一致，保留该往返作为工作流局限。

S03.C03 仍是 U14 实际比值的 AST，最后已保存数学检查返回 3/PASS；U14 正文与 101 请求基线逐字相同。核算记录里保留旧限制说明属于历史，repair-6 新限制明确说明“仅保留比较思路”描述的是旧候选，不能误认当前正文仍缺两方向。

计数要分层：此时 S03 section applied_rounds=6、proposal_calls=6，不等于每个单元修了 6 次。实际累计 unit_applied_counts 为 U12=3、U10=2、U09/U13/U06/U14 各 1；本次恢复只给 U12 增加 2 次。此前 U14 的核算 AST 修订也按对应单元计入预算，不可把计数直接当作正文数学错误数量。

## 114 请求：S02.U14 的确定指标误报

本轮 `runs/fd6736af6ef14be3839e019e86ca1e5c/global-8c697e38-0-review-0.json` SHA256 `b134c18b7af03ffdd020a2313ce96f168ea5e91f74bbb8cd1abcf7d082c863cc` 将 U14 标为 blocking，认为假设 n>N 时 a_n=b_n，只能在 n≥N+1 得到 `B_n−A_n=Σ_(k=1)^N(b_k−a_k)`，要求把原 n≥N 改窄。

独立判断：原 n≥N 完全正确。n=N 时该式直接由 A_N、B_N 的定义及有限和相减恒等式成立，根本不需要尾项相等；n>N 时其后的差项全部为零。模型举的 N=1、a_1=0、b_1=1、其余项相等的例子，两端均等于 1，恰好验证恒等式，而非反例。原 U13 也明确 N 是正整数，没有 N=0 未定义部分和问题。

受审正文候选 `local-repair/S02/candidate-0636aaa67e80.json`，SHA256 `d0d1ecb1b60e318b6042f4b63eb779a84dbbb2b3fe58a8e5923de5f4a4b8ee87`。这不是跨单元引文错归，也不是核算 AST 问题，而是审阅模型对一个边界恒等式的推理错误。若后续仅收窄到 n≥N+1，修改后的证明仍足以说明极限，但应记为无必要收窄；绝不能统计成原证明存在真实数学错误。发现时只取证和通知父任务，没有修改正文、重试或新增 API。

## 后续待核对

112 请求快照 `CH02-post-thirddeploy-tracking/snapshot-20260920-184653-104974.json` 已确认五节重新 CHECKED：rowid 52/53/57/58/59，候选与检查点完全一致。S03.U12 的恢复稿经过后续本地审阅、数学工具及实际 Windows 节编译后接受；S04、S05 仅重查，没有新正文修改。相较 101 请求基线仍只 U12 有改动，先前两条反馈落实保持。任务进入 GLOBAL_REVIEW，尚未产生新逐项反馈回执。

继续追踪合法候选、检查状态及逐项反馈回执，记录受审输入正文与当前候选的差异。到 AUR 或确定阻塞再向父任务提交最终状态、产物 ID 与 PDF/TeX SHA。每条反馈须有实际完整回执及正文依据；当前尚未进入新逐项反馈阶段，不能宣称两项已由新协议评估完成。

## 118 请求：全局越界保护正确阻断，尚未取得最终交付稿

2026-09-20 18:57:22 UTC，任务停为 BLOCKED / repair.global.S02，错误 GLOBAL_REPAIR_SCOPE_VIOLATION。最终状态快照 `CH02-post-thirddeploy-tracking/snapshot-20260920-185837-077745.json` 保存所有恢复事件、合法候选、全局待修状态及产物身份。五节仍为 CHECKED，rowid 52/53/57/58/59；相较第三部署前只 S03.U12 已实际变更。S02.U14 正确的 n≥N 仍保留，新的拒绝提案没有进入当前候选。

拒绝提案位于 `runs/fd6736af6ef14be3839e019e86ca1e5c/global-repairs/r3-a84bbd84/`。`S02-ec86609b-before.json` SHA 为 `d0d1ecb1b60e318b6042f4b63eb779a84dbbb2b3fe58a8e5923de5f4a4b8ee87`；raw 与 normalized 均为 `21e16431dd0df3f434f2b22fec73992035a3514cf9ce6b7beb7aacc4b8cc3613`。

完整前后差异与对实际 AST 的离线算术核验保存为 `CH02-global-r3-rejected-proposal-evidence.json`。模型将允许目标 U14 的 n≥N 改为 n≥N+1（两种写法均足以完成证明，改窄没有必要）；同时错误重写了非目标 U16 的核算 S02.C03：原 lhs 是 `2*(1−2^(−n))+2`，提案变成 `2*(-1)^(2*(-1))+2=4`，rhs 仍为 `4−2^(1−n)`。实际 AST 在 n=1 取值，原两边均为 3，提案为 4 与 3。这不是字典键序或纯格式差异，保护门禁拒绝是正确行为，不能放宽后采纳。

全局状态仍为 repair_pending、rounds_used=3、pending S02.U14，批准计划及合法正文未重置。新增误算未被数学核算接受，不能声称“第三次修复成功”。原最初 n=N 误报的独立有限和核验另保存 `S02-U14-false-positive-boundary-evidence.json`：模型自举“反例”左右都等于 1。

无当前非 superseded 的正式 lecture.pdf。最近累计 Windows 节编译 PASS 为 18 页，PDF `b/fd6736af6ef14be3/sS05_e006d02d6134/build/lecture.pdf` SHA `d6e802cdd5f3f38ec71b0a4239259488a8cc83b1b49211ac7b789d1b65247819`；TeX `b/fd6736af6ef14be3/sS05_e006d02d6134/source/lecture.tex` SHA `b5b6052c32a63e36bb01eb89ea3a1b3ab9999e0ac99976f5ffa24e23d8898f82`。它不是最终 AUR 交付稿，本审计没有进行最终页面图像查看。

新逐项反馈阶段尚未执行，feedback.reviewed 回执为 0 条；不能宣称本次新协议已确认两项反馈 satisfied。父任务已收到阻塞和具体差异，决定修复全局整节输出的风险并保留旧状态迁移；本审计未自行重试或改稿。后续恢复必须继续保留本次失败、计数与证据。
