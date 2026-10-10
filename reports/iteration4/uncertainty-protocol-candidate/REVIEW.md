# 疑点协议候选：冻结裁定重放

候选范围只有 provider 的 reviewer_uncertainty 窄 JSON 解析、疑点裁定权限分离和精确已知契约的冻结重放。未修改生产源码、数据库、正文、预算、审批或 global V2 identity。

- CH02：无定位旧声明允许由真实 current 证据消解，保留 unit_id=null；open_actionable 仍必须绑定真实目标。普通数学问题和工具 UNKNOWN 不由此删除。
- CH03：只接受完整无重复键 JSON 对象之后至多4个纯闭括号（尾部总长不超过32字符）；其他文本、第二对象、截断、重复键、非有限 JSON 常量拒绝。原响应归档，schema/逐字引文/SHA仍检查。保存的 open_dependency 不改写为通过。
- 旧 INVALID 仅精确白名单契约迁移；同 plan/body/input，原普通审阅和所有依赖 SHA，原 INVALID 事件回执，以及相同 call/context/prompt/schema 的请求—传输成功—结果链必须匹配。CH03 原 archive 必须属于该 run，字节数、archive SHA及原响应 SHA相同。新账本保存来源，旧账本不改；无新 API 裁定；新正文才能正常新审阅。
- 迁移证据、状态和事件各崩溃边界可恢复；未知/损坏来源、失去租约和数学审阅规则变化不自动重抽。

最新严格离线测试：validation/fifth.xml 记133 passed，1 real_api deselected，0失败/错误。runner清除所有 MATH_AGENT_* 与 OPENAI_API_KEY，并拦截非loopback socket/DNS；runtime记录外网尝试0。这是 mock/冻结真实响应重放测试，没有执行本候选的实际Windows编译、agent全页视觉或教师验收；生产迁移尚未执行。

必须保留的前轮限制：first为隔离包导入收集错误；second为默认临时目录权限错误；third针对性89通过。fourth未清除继承环境，导致7个传统MockTransport用例被流式/多模型设置污染而失败；同时遗漏排除real_api，意外执行并通过1个真实连通性测试。该测试未归档逐请求细节，不能断言外部请求次数，也不能据此声称数学质量通过。完整日志和XML保留。fifth已修正隔离，不能删除或合并前轮记录冒称全程0 API。

READY manifest位于 ../uncertainty-protocol-manifest.json；独立审查由 recovery_evidence 进行。最终合并后应重跑完整与Edge验收，并在正式retry中核对原账本仍在、迁移事件存在和CH03仍要求真实证明修复。
