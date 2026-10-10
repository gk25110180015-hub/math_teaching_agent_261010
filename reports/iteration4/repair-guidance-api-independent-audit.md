# 修复指导 API 独立静态审查

2026-09-22。审查范围为 root 提供的三个 API 候选，未改生产源码、测试或数据库。此项为代码审查，不能代替正在准备的 API 测试或真实任务验收。

| 候选 | SHA256 |
|---|---|
| domain.py.candidate.py | 446502903a1277ca44c7a637f2976469fa1a8720edcf92376ac8f755e4e28989 |
| service.py.candidate.py | 93a321e7ed967eb7150a9018c370e18c1c00928ae85f3e01a56d66c8abf314a9 |
| web-app.py.candidate.py | a08d8b122637b24d261b5d0854c2f715986974fa43fca64490073e12200c498a |

这三个文件范围内未发现阻断问题：

- `RepairGuidanceRequest` 使用严格、禁止额外字段的 schema；指导去掉首尾空白后至少 20 字、最多 20000 字，单元 1–8 个且不重复，候选哈希为 64 位小写十六进制，来源明确。
- 新操作沿用本机 Origin/Host/session/CSRF 边界；服务仅允许明确本地操作 actor，不把建议作为审批或人审。
- `request_repair_guidance` 全程处于现有 `BEGIN IMMEDIATE` 事务。先核对当前计划版本和哈希，然后判断幂等动作；同 action_id 不同有效请求拒绝，同内容返回原 job，不重复指导事件或重排。
- 新动作必须是 BLOCKED/FAILED 的讲义、无 queued/running job、保有同输入/同计划的原批准。helper 返回的真实候选语义哈希必须与请求相等，所选单元必须是该候选的实际单元。提交事件记录候选文件 SHA、恢复状态绑定、原请求数及预算版本。
- 指导事件和 `_retry_locked` 属于同一事务；历史预算不明确、预算不足或无失败任务时会整体回滚。它重排同一失败 build job，不创建替代任务，不改批准，不清空累计请求或修复次数。租约清理沿用既有重试，后续 claim 仍增加 fencing token。
- 幂等返回前保留当前计划校验，并拒绝取消/发布任务。此分支只读取既有 job，不在重放时覆盖正文、候选或新指导内容。

需由 API 测试确认的运行事实：同 action 重放只产生一次事件和 retry；冲突 action、错误候选、失效计划、缺少审批、活动任务及预算拒绝均无部分写入；原 job/审批/计数不变；202 路由遵守本机认证要求。上述是明确测试目标，本文不声称已执行。

跨模块发现另已通知 root：初读的 `repair_guidance._sync_global` 将受指导候选存到 `global-repairs/guided-seeds`，而现有 `global_repair_contract._validate_state` 要求 section 候选位于 `state.round_directory`。若不协调，指导采纳后的下一次全局状态加载可能拒绝这个指针。此点属于 helper/恢复契约集成，不在这三个 API 文件中；统一部署前须核实修复，并覆盖“指导采纳后再次加载/恢复”场景。

真实模型、Windows 编译、浏览器 API 集成和教师审核：本次独立审查均 NOT_RUN。此前九项 UI 浏览器检查使用合成接口，记录另存，不能替代此 API 验收。
