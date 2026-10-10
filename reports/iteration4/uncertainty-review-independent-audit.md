# 声明数学疑点显式处置：独立审查

状态：INDEPENDENT_REVIEW_PASS，最终候选在窄方案 A 范围内未发现剩余部署阻断。本报告不改生产代码、原稿、生成正文或任务数据库，不调用模型 API，不批准新增先修条件或发布未解决重大疑点的讲义。

## 当前代码边界

新 helper 给原 uncertainties 的每个出现位置建立稳定 ID，保存完整原文和哈希；仅以实际单元 ID 在首个非空白位置加明确分隔符正向绑定。`.answer` 等实际 ID 合法；正文中提及、错误前缀、不存在或不明确归属不猜测。原数组不删改，原 check_math 报告保留。

独立 schema 逐项覆盖全部固定 ID，区分 resolved_by_current_body、open_actionable、open_dependency；引用必须属于实际提供源且 SHA 与逐字引文匹配。resolved 不允许 remaining_dependency=true；可行动项必须含当前目标引文及修复指令；未知归属不能获得定点修复许可。处置仅是有证据的模型判断，不是形式化证明或教师验收。

普通 MathReview 先冻结再请求新裁定，处置 ledger 绑定批准计划、完整正文、实际依赖和工具证据及相关契约；job、模型偏好和普通审阅措辞不作为重新抽取的身份变化。原普通 blocking/review 和工具 UNKNOWN 应继续阻断。新的实际正文/依赖才可对应新数学事实身份；预算与原 LocalRecovery 接受/提案/拒绝计数保持原流程。

## 已指出的两个具体问题

1. 首版 Pipeline 在合并普通 review 后，以 rule_id 全量删除 DECLARED_MATH_UNCERTAINTY，再加入显式处置集合。当前严格 MathReview schema 本身不允许 rule_id，因此标准模型响应暂不能直接利用此路径；但对来源未知/旧记录同 rule 仍不能推断为作者声明。旧记录映射也不能仅凭 rule_id+相同文字或已知 uncertainty_id 删除。已要求只替换准确构造的工具声明集合，旧记录须核对实际报告中的精确工具形状或既有处置 ledger 来源；其他问题原样保留，并补负测。
2. 首版 evaluate 在 provider 对完整坏 JSON 抛 INVALID_MODEL_JSON 后，先登记 failure-N.json，再写终态 INVALID。若在这两次 state 保存之间中断，重启得到 STARTED、无 response_file，却已有明确不可重试失败；首版会 calls++ 再抽一次裁定。已要求在任何新 generate 前消费已登记的当前 failure 记录，非 retryable 恢复阻断；仅 transport/budget 可用冻结输入续传输，并补保存失败证据后中断的真实恢复回归。已保存完整 response 的校验失败原本会重读原响应，不存在相同的重抽窗口。

最终两项都已修正并核对：Pipeline 只替换本轮实际构造的声明对象；旧记录须由报告 math 哈希与原 review identity 一致，且原 issue 精确存在于该已核验工具报告，或确为报告中保存的无类型重复。未知同 rule/已知 ID 问题保留。失败恢复先检查当前登记的 failure-N，不可重试则恢复 INVALID，不调用模型；可重试仍用冻结输入，孤立未登记失败证据阻断。新增同 rule 来源负测、完整坏 JSON 保存失败后中断与纯传输同位置中断回归均通过。

一个明确非阻断的可观测性局限：最终 REVIEWED state 已原子保存而 math.uncertainty_reviewed 事件尚未发出时若中断，重放可读完整 ledger，但当前实现不保证补发该事件。因此 ledger 是恢复证据，不能声称事件必达；这不使未知结论变为通过，不重置预算，也不产生新模型抽样。

## 数学与范围限制

CH03 当前指数不等式的条件性调用不能仅凭“已经假设”当作不等式已证。批准计划中的“指数函数、对数函数和三角函数的基本性质”不能自动作为该精确命题的出处。独立数学备忘 `CH03-exponential-inequality-independent-note.md` 给出有限二项式、Bernoulli、Euler 定义与有理幂延拓下的一条非循环路线，同时明确这些是必须声明的依赖；本备忘没有注入生成稿或充当已批准来源。模型可判断批准范围内是否能补充实际证明，或保留明确 open_dependency；不能靠该新协议把外部前提换名为已解决。

## 验证状态

最终证据为 `uncertainty-validation/20260920-192956-044419`：153 项本地/mock PASS，20.12 秒，含 44 项新增与 109 项既有，API 调用 0。独审核对 context、result、pytest 日志、JUnit，并重算 4 个 manifest 候选与实际隔离包文件 SHA，逐项一致，Python 语法解析通过。新增测试文件 SHA=`ca542ff84f11e3795f00a8c14762ce63aef0ce8d15924d0a8ff01104e05417fc` 与运行 context 相同。测试含真实隔离 SQLite、正式 Service.retry/claim 恢复、普通问题冻结、预算/传输保持、声明修复后的新正文消解、坏结构只请求一次及上述中断窗口；compiler 与模型均受控替身。

冻结 SHA：helper=`288a374421c952020165b4ec12585e98e4dc5948dacad3d49df759e342f632e2`；Pipeline=`f149aada793e898fd9fc37f14975e6cbb911ec9d7406a7d75f4d72d24e6d4792`；provider=`556b85726acc7f11318dd6aa21a2e7e2a304f5c5d7c78ecb89adaec72db372d6`；prompt=`5c0f40881c0ef1be2c5c26d1e67865280ee0b7ddd3bcb2b2bc6ebfab77a28c39`。与全局严格补丁叠加后的整体 Pipeline 尚需部署方验证及回归，不能把两个独立候选测试直接当作组合结果。

首版 125 PASS、后续中间测试是历史证据，不与最终 153 累计。真实 API、Windows 编译、实际生产恢复、最终 PDF 视觉与教师验收在本独审中均 NOT_RUN。即使真实恢复输出合法 resolved，也只能记录有证据的模型处置，具体数学与教学质量仍须独立复核。
