# 数学疑点协议恢复独立审查

2026-09-22，只读审查。以下候选已与作者确认冻结；未改生产源码、真实数据库或旧响应，也未自行重跑模型或测试。

| 文件 | SHA256 |
|---|---|
| provider.py | adaac69a8e12ff4956a8b251170176ab3cae80da787bd7f76bd729f116303685 |
| uncertainty_review.py | 2014e3aec411c6aced3fe0f16e38323397bbd9b5a44e0841fe1a800157511187 |
| uncertainty_protocol_recovery.py | fcb647c4ba2d5cfbda92485ba9a6d284eed9e4ab611f0117a76baf231d77cd15 |
| test_uncertainty_protocol_recovery.py | 58f7298e086909ee3f0c955b973a9050592d6cc1b1b66458172e1b9970e6a2a5 |

未发现该版本恢复逻辑的阻断问题。结论限于实现审查及已保存测试记录核对，不是数学内容、真实 API 或教师验收通过。

冻结重放只接受同一数学 context、计划哈希及修订号下唯一旧台账。旧台账必须完整匹配显式白名单 v1 契约，状态 INVALID、一次已完成调用、失败不可同槽重抽。未知或多个契约、遗失旧状态、改动的输入/普通审阅/依赖字节均阻断；没有“迁移失败便调用新模型”的分支。新正文属于新的数学输入，不能伪装成旧裁定重放。

旧台账 state SHA 必须对应原 `math.uncertainty_reviewed` INVALID 事件。恢复重新构造原 prompt/schema/messages 的 input_hash，在原调用时间窗内核对唯一 request → HTTP 200/成功完整传输 → 同 call_id 的结构输出或原失败归档链，模型/base URL/首选模型必须一致。CH03 原 archive 必须处于该 run 的 provider-failures 目录，文件 SHA、长度、原响应 hash 全部相等；不是从任意日志猜测裁定。不能把 HTTP 200 响应头单独视为完成。

序列化恢复只用于 `reviewer_uncertainty`：已经完整结束的单个 JSON 对象后允许 1–4 个多余闭括号（尾段总长最多 32），不更改对象内容。重复 key、多个对象、正文说明、截断、未关闭对象及非有限常量拒绝。提供商保留原响应及恢复记录；其他审阅角色不获得这项宽容。CH03 冻结文本确有末尾多余闭括号，合法对象内裁定明确是 `open_dependency`、`remaining_dependency: true`，无修复指令；迁移后仍产生原数学疑点，不能当作证明完成。

CH02 的修正允许有逐字当前正文证据、无未核实依赖的旧无定位声明被自动裁定消解，仍保存 `unit_id: null`，不猜归属、不授予引用单元修复权。原声明、原疑点记录与普通数学审阅保留。这个自动裁定不是形式证明或教师审批。

新迁移台账含旧来源身份、旧依赖、三条提供商事件及其哈希、响应/裁定 hash 与零新调用标记。MIGRATING 各保存边界通过相同冻结材料恢复；已完成迁移再次载入仍重新核对旧来源。写入持有 job fence，事件唯一性校验不会把重复或冲突回执静默吞掉。

已核对作者的受控第五轮记录 `uncertainty-protocol-candidate/validation/fifth.log`、`fifth.xml` 与 `fifth-runtime.json`：133 PASS，1 real_api 排除，外网尝试 0，测试进程凭据已清除。测试覆盖两章真实保存响应的离线重放、未知/损坏/未绑定证据拒绝、四个崩溃边界、租约丢失、普通审阅政策改变及角色限定。该数据不能与第四轮相加为纯 mock 结果：作者已说明第四轮 runner 环境隔离失误意外运行 1 个 live opt-in 测试，并出现 7 个环境污染失败；这些原日志须保留，不能据此断言实际外部请求次数。

采集器尚需配套补充：本候选重放完成发出 `math.uncertainty_migrated`，现有只读 collector 的疑点归档只索引 `math.uncertainty_reviewed`。统一部署后的最终采集应追加新迁移台账、旧来源与归档调用证据的归档核验，不能仅保留旧 INVALID 台账就宣称新迁移证据齐全。该扩展不应削弱既有当前反馈/最终正文绑定，也不能把自动 resolved 显示为教师批准。
