# 同审批全局修复契约变更门禁

本次新增 `tests/test_global_contract_guard.py` 四项离线回归。真实 SQLite、Service 审批和请求账本配合 mock 模型、mock 编译器，不调用远程 API。

同一批准计划的 repair prompt、WrittenSection schema、normalizer 身份哈希变化分别验证：加载时明确返回 `GLOBAL_REPAIR_CONTRACT_CHANGED`；状态文件字节、已使用的两轮全局修复、原未决疑点、审批、累计请求数均保持不变，不调用新模型。

另一项通过 Store 保存不同计划并由真实 Service.confirm 显式批准，验证新计划获得 `not_started`、零次全局修复和空问题集；旧状态文件保持不变，整个任务的累计请求数不会清零，也不产生人工审核记录。

旧生产实现红测：**3 FAIL / 1 PASS**，失败原因均为未阻断同计划契约变化，详见 `global-contract-guard-red.log` 和 `.xml`。

父代理统一部署后的实际生产源码回归：**4 PASS，3.62 秒**，详见 `global-contract-guard-deployed.log` 和 `.xml`。Pipeline SHA-256：`504e66ea5d2abaec818deafa3420ec70db82fbdee59638fed1c64e8383250fa8`。这次验证直接运行已合并模块，并非隔离候选。

真实 API、Windows 编译、教师数学/视觉验收：上述四项测试均 **NOT_RUN**。完整 Edge / Windows 编译回归另存 `full-e2e-deployed` 的独立证据目录，不与本组 mock 回归混计。

剩余边界：现 guard 先使用当前 WrittenSection schema 校验旧候选；未来若 schema 有破坏性变更，可能先返回 `GLOBAL_REPAIR_CACHE_INVALID`，而非契约变更错误。它仍保留证据且阻止采用/清零；本轮未改变 schema。完整契约迁移不在本次实现范围内。
