# 严格局部补丁与可恢复合法稿验证

本次由实际 CH01-S04、CH03-S03 的整节修复越界失败触发。旧 `repair-2-raw.json` 继续保留并拒绝，未将其中越权改动抹去后当成有效响应。未来通用 LOCAL 修复使用 `repair_local_patch`，只返回允许单元的正文和受控核算补丁；全局修复的正文协议未改变。

## 实现边界

- `local_patch.py` 保持全部单元 ID、kind、顺序、relates_to 和非目标正文，核算按已有 ID/原 unit_id 更新，新增核算只能绑定目标，禁止删除原核算；疑点和限制只能追加。
- `local_recovery.py` 在原任务 `local-repair/SID.json` 持久化候选路径/字节 SHA、审批计划与上下文身份、每单元已接受修改次数、累计提案/拒绝、未决疑点、引用/答案提案证据依赖。候选及状态历史使用独立不可覆盖文件。仅普通检查和实际编译成功后才能进入原有 CHECKED checkpoint。
- 恢复一份合法局部稿仍重新执行排版归一、校验、数学核算、模型审阅和编译。相同正文、工具结果、审阅提示和计划上下文不能用一次不同审阅随机清空已记录疑点；实际证据或审阅提示改变时保留前后身份与问题供明确重评。历史提示哈希缺失记作 UNKNOWN_NOT_ARCHIVED，不补造旧版本。
- 旧流程迁移只沿已验证 writer 指针读取连续 repair 链；校验原归一化哈希、before/after 链、原 raw 经当前归一化与已应用稿一致，以及严格目标范围。原候选、normalization、normalized、每次 raw/review/applied 和末次 review 全部成为后续 SHA 依赖。缺指针、损坏证据、链断裂或不一致会阻塞，不按文件时间猜稿或清零。
- 初始接受修改预算按**单元**计算；正文或绑定核算改变均消耗该单元一次，默认最多 2。不同单元不共用整节 2 次上限。每目标 key 提案最多 limit+1，保留所有拒绝；一次拒绝可继续，第二次拒绝后不再自动提案。结构补全使用 `label:<label>` / `answer:<exercise>` 独立 key，避免 CH02 新增答案占用原练习最后一次正文修改机会。累计提案数不冒充实际模型请求数，后者仍由 Store 逐次计数。
- 单元/全文上限读取持久有效预算，全文独立默认 2；耗尽统一 BUDGET_EXHAUSTED。显式用户增额可提高上限但不清计数、审批或问题。Pipeline 为基准驱动另传 `request_budget_hard_cap`，运行持久预算不能突破调用者独立总额上限。此次未对任何真实任务增加预算。

## 三条实际失败样本

受控离线 fixture 保留原正文和原始文件 SHA，不改真实目录：

| 样本 | 验证 |
|---|---|
| CH01 S04 | 合法 repair1 修改 U04/U06，各计 1；非法 repair2 未采用；旧未决 U04 疑点保留。 |
| CH02 S02 | 合法 repair1 修改 U18/U19/U20，各计 1；旧新增单元的 repair2 未采用。独立追加答案后，仍允许最后一次目标练习正文修改；合计 4 次提案中旧 2 次没有丢失。 |
| CH03 S03 | 合法 repair1 修改 U04/U06，各计 1；非法 repair2 非目标 U10 标点未采用。离线构造符合新协议的 U03/U06 与 C01 补丁后，U10 完全不变；真实 SymPy 检查从 NEEDS_REVIEW 到 PASS，只支持该核算，不等于全文数学验收。 |

三个旧链测试在独立临时库明确初始化每任务 60 上限，并设置 synthetic 历史计数 26 来验证计数不变。这是测试夹具，不回写实际 CH02/CH03 请求次数，也不声称其实际历史计数均为 26。

## 执行证据

| 日志 / XML 基名 | 实际结果 | 分类 |
|---|---|---|
| `local_recovery_initial` | 93 PASS，4 FAIL，2 deselected | 初轮保留：冗余归一调用、恢复后的审阅次数预期及提案依赖 SHA 缺口；已修复并复测。 |
| `local-recovery-02` | 108 PASS，2 deselected，40.25s | MOCK provider/compiler、真实 SQLite 与 SymPy；未运行 Windows 编译标记。 |
| `local-recovery-03` | 115 PASS，0 skipped，60.42s | 含 **3 项实际 Windows XeLaTeX 编译**：严格局部补丁流水线、真实标签样本编号、独立答案及 PDF 回链；其余 MOCK/真实本地检查。 |
| `local-recovery-final` | 28 PASS，1 FAIL，2 deselected | 新 002 迁移使旧 `test_state` 固定一条迁移的断言失效；实际得到 2，原失败日志保留。 |
| `local-recovery-final-02` | 29 PASS，2 deselected，13.77s | 明确检查迁移版本 `[1,2]` 后状态、CH02、hard cap 和显式增额回归通过。 |
| `local-recovery-real-fixtures` | 4 PASS，15 deselected，1.34s | 最终三章 fixture 明确初始 60；审阅失败后实际 Store.retry + 新 Pipeline 恢复合法稿。 |

所有命令显式使用 `MATH_AGENT_API_KEY=''`、`MATH_AGENT_LIVE_API_ENABLED=false`、`MATH_AGENT_LLM_STREAMING=false`，独立短路径 `workspace/t/lr*`。真实失败 API 产物仅作为只读离线样本；**本次真实 API 测试 NOT_RUN，教师视觉/教学验收 NOT_RUN**。测试角色的用户扩额是 synthetic action，不能当作实际用户授权或教学审批。

此前 369 PASS 全量快照不覆盖本次新增局部协议及预算界面。本文只报告上述定向结果；整体最终回归和预算 UI 浏览器验收由主任务在各模块冻结后独立记录。
