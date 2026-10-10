# 全局严格局部补丁与已知 v1 状态迁移候选

状态：**READY_FOR_REVIEWED_DEPLOYMENT**，最终隔离回归和[独立审查](global-strict-patch-independent-audit.md)通过；**未部署、未迁移真实任务、未调用模型**。生产源码、生产测试和 scripts 未改。最终部署必须采用 [候选清单](global-strict-patch-manifest.json) 的基线与候选 SHA，不直接复制较早的临时包。

## 实际触发和修复范围

CH02 第 118 次请求后因 `GLOBAL_REPAIR_SCOPE_VIOLATION` 阻断。全局第 3 轮只允许修改 `S02.U14`，但 `repair_content_unit` 返回整节时，同时把属于 `S02.U16` 的 `S02.C03` 核算 AST 改错：原表达式在 n=1 得 3=3，错误提案变为 4≠3。原范围检查正确拒绝，错误提案没有被采用。[完整原始证据](CH02-global-r3-rejected-proposal-evidence.json) 保存 before/raw/normalized 及 SHA；新的回归 fixture 是这些保留值的复制，没有改原件或把错误提案当基线。

候选只把全局修复请求改为既有 `repair_local_patch` + `LocalPatch` + `apply_local_patch`。模型返回授权单元的 `{unit_id,tex}` 和必要的对应核算更新/追加；程序复制原节并应用补丁，不从模型整节中偷偷截取目标。完整 `WrittenSection`、非目标正文/核算、ID/顺序/关联/原元数据变化均拒绝。只规范化目标正文，再独立核验范围、保留旧疑点/限制的前缀，然后进入原数学、依赖和编译检查。追加疑点不表示它已解决。

原数学审阅提出的 U14 端点疑点保持原文与原范围。本候选不裁定其数学正确性、不重新抽取旧审阅来清除疑点，也不放宽普通数学门禁。相关数学反例核实由独立证据保留。

## 狭义、明确的状态迁移

新全局修复 identity 为版本 2，记录补丁提示词/schema/验证器、核算协议、WrittenSection schema、规范化器与迁移代码的 SHA。迁移只接受旧 identity **整个对象精确等于**当前 plan/model/provider 加以下已部署 v1 值；额外/缺失/未知字段均不匹配：

| v1 字段 | 固定值 |
|---|---|
| repair_prompt_hash | `46c1ff3b8ea3f0fba7afe1f6a3b99f3286324551522140dc61d8b646807759f9` |
| written_schema_hash | `4e9b07e27f359212c0460381e3cbd6e548d18a48490e553e60b0c56d30d9ada7` |
| normalizer_hash | `25d2fff448b21fcad71b5e7aae512cf6ab27f66bdeefd9e459ca57652a1fd74c` |

当前 WrittenSection 和 normalizer 也必须仍匹配这两个固定哈希；没有“使用当前文件推测任意旧版本兼容”的回退。不同批准计划沿用现有 fresh-state 规则；同一计划未知契约继续 `GLOBAL_REPAIR_CONTRACT_CHANGED`。

迁移保留旧状态全部业务字段：phase、rounds_used、issues、pending 及邻节上下文、sections 的路径和 SHA、原候选、教师未审核状态。只改变 schema_version/identity，并增加审计标记；不清轮次、不修改 request_count、预算、输入或审批，不回滚已接受内容。合法 `sections` 是从首个受影响小节开始的子集，不要求覆盖全章。`repair_pending` 在原轮次直接请求补丁；`checking` 使用已接受稿继续原检查；`validated` 保留轮数，随后由现有新版章节契约触发实际重检，不直接沿用旧 PASS。

迁移前还核对状态形状、严格整数轮数、已知 phase、受控 round 目录/候选 SHA、pending 的真实单元与原问题一一对应、批准的相邻小节上下文。实际批准计划完整内容、revision/hash、input_hash 和 approval 行必须一致。迁移后每次读取仍验证当前形状，当前轮数不得低于迁移前已用轮数。

## 可恢复审计事务

每次迁移在有效 worker fencing token 下执行，使用确定的迁移 ID。在任务 `global-repairs/contract-migrations/<id>/` 保存不可覆盖的：

- `before.json`：原 state **原始字节**和 SHA；
- `after.json`：迁移初始 state 原始字节和 SHA；
- `evidence.json`：批准身份、原请求数/轮数/phase、pending 授权范围、前后契约、原业务字段摘要、job 和时间。

写持久日志后才原子替换当前 state，再记 `global.repair_contract_migrated`。若日志后、state 前中断，重试验证不可变记录后继续；若 state 后、数据库事件提交前中断，下次读取在验证原始状态/新状态/日志/当前批准与计数后补记**同一事件一次**，不再迁移、不请求模型。已存在事件须与日志相等。文件损坏、不相符的事件或当前轮次回退均阻断；不会覆盖坏证据或退回旧 PASS。

晚到补丁可以留作诊断，但发布 candidate 指针和移除 pending 前必须再次通过 fencing 检查。请求计数仍由现有 provider 在调用前计入实际持久预算；全局原轮次不因补丁形式改变而重新分配。

## 文件影响

生产代码仅两个文件：`pipeline.py` 的 global identity/load/continue 及检查契约模块列表；新增 `global_repair_contract.py`。不改共享 LocalPatch、WrittenSection、普通 MathReview、数学/修复提示词或预算配置。

四个已有测试候选只适配全局 provider 的请求/响应形状：global_repair、global_budget_resume、teaching_quality_gate、recheck_feedback_history；原全节越界负例仍返回完整非法对象，要求严格拒绝。新增 `test_global_strict_patch_migration.py` 与捕获 CH02 AST fixture。全部目前只放在 reports，清单给出将来对应的 tests 目标及原 SHA。

CH03 不确定性定位/逐项裁定由另一窄候选负责，根任务将在停止的服务上把其 pipeline 片段与本候选顺序合并；本文件不为该独立功能声明通过。

## 实际验证记录与限制

| 记录 | 实际结果 | 解释 |
|---|---|---|
| `global-patch-validation/20260920-191104-fada21` | 31 失败 | 初次新夹具错误地把 Settings 默认全局上限设为 6，未进入业务验证；已改用正式 Service 增额 2→6 后重试。保留失败，不当作有意义红测 |
| `global-patch-validation/20260920-191157-fed118` | 基线 21 FAIL / 10 PASS | 有意义红测：旧 pipeline 仍请求整节，没有显式迁移、形状和持久审计恢复 |
| `global-patch-validation/20260920-191219-b39a6e` | 候选 29 PASS / 2 FAIL | 两项夹具问题：内存邻节与 plan 共用对象，修改错误地同时改 plan；误假设请求限额 60 而实际持久默认 120。改为独立反序列化语义和读取有效预算；未放宽产品门禁 |
| `global-patch-validation/20260920-191327-4149c6` | 187 PASS、1 Windows 编译排除、0 外网尝试 | 对应独审补强之前候选，不代表最终新增轮次下界/journal 验证已通过；模型/编译为 mock，真实 SQLite 与有界 SymPy 核算 |
| `global-patch-validation/20260920-191738-e00135` | 194 PASS、1 Windows 编译排除、0 外网尝试 | 新增当前轮数下界、journal 上下文、真实可达 validated 检查点恢复；之后又收紧 pending_scope/非负请求数，不拿这次替代最终版本 |
| `global-patch-validation/20260920-192019-2329bb` | **最终隔离候选 196 PASS、1 Windows 编译排除、0 外网尝试，45.62 秒** | 含 40 项新增迁移/严格补丁测试及 156 项相关旧回归；src/tests 基线 SHA 未变。仅测试 SQLite、mock provider/compiler、有界 SymPy；保留两条依赖弃用 warning |
| `global-patch-live-shapes-20260920-191531-0d79f5.json` | CH02/CH03 只读形状和候选 SHA 均 PASS | CH02 phase=repair_pending、rounds=3、S02—S05；CH03 phase=checking、rounds=4、S03—S05。均精确匹配已知 v1；只读文件及初始审批报告，未访问 DB、未执行迁移 |

最终这次测试绑定 pipeline SHA `bc99fd54a18fa71aaae1cac1bd3c554d593a04bd18a34701343c6d613992b2b5`、迁移 helper SHA `8c1167ba608adbc1b74d9fe4d5852152eba74069606c466a4c2db606c8df2186`。独审反馈已补充当前状态形状/轮数下界、预提交 journal 的审批/输入/计数一致、pending_scope 精确来源及请求数非负；新增测试没有通过放宽旧断言消除问题。旧测试数不累加，修改后的候选不能复用先前 PASS。

真实 API、实际 Windows 编译、Edge、真实任务迁移与续跑、教师审核：本候选阶段均 **NOT_RUN**。根任务统一部署后才可实际恢复两章，最终交付需要另外的编译、文件 SHA、语义与视觉验收。
