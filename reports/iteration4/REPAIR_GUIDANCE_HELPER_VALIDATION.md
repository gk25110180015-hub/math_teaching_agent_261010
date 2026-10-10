# 限定单元修复指导：候选与验证

状态：READY_FOR_REVIEWED_DEPLOYMENT。仅报告目录候选，生产文件未由本子任务修改。

指导绑定原计划、原 job、实际候选语义哈希与文件 SHA、局部恢复状态及原审阅证据。它进入现有 LocalPatch 模型上下文，不是正文注入、教师批准或新增先修授权。候选仍须执行数学核算、普通审阅、疑点裁定、局部编译及后续全章检查；旧声明疑点和未决数学问题不由指导动作删除。

当前最小范围仅支持 BLOCKED/FAILED 的 lecture 任务、可核验的当前 section 候选、没有等待中的 global pending。指导不能改变原审批、预算或累计单元修改次数。无正文/核算变化的提案和越界提案会保留并拒绝；同一动作不会重新抽取已拒绝的提案。

每个动作保存 before/proposal/after、规范化和局部补丁证据。recovery-before.json 和可选 global-before.json 是事件所绑定状态文件的原字节快照，dependency SHA 必须等于事件中的绑定 SHA；它们不是对 dict 重新序列化的近似副本。初始化中断后，已落盘但尚未注册的快照只能按原绑定 SHA 恢复。接受标记与 LocalRecovery 状态一同保存；接受后、全局指针同步前崩溃时，可在下次载入 forced seed 前恢复。新全局候选保留在原 state.round_directory，原全局轮次、问题、契约迁移证据保留。没有放宽 global_repair_contract 的目录守卫。

最终隔离回归：`repair-guidance-validation/20260923T020005-422200`，**146 PASS、0 FAIL、0 SKIP**。包含新指导测试 20 项，以及既有 local recovery、global patch/migration、uncertainty、global repair/budget 测试。模型调用全部注入 mock，真实 API 0 次。其中 `test_strict_local_patch_is_rechecked_then_actually_compiled_on_windows` 实际运行 Windows XeLaTeX 并通过；其他测试中的编译为 mock。教师数学/视觉和本轮最终讲义逐页视觉均 NOT_RUN。原字节补充前的 145 PASS 记录仍保留在 `20260922T150012-787500`，不替代本版结果。

新测试覆盖：严格目标范围、保留其他单元和旧疑点、原审批/计数、空补丁与坏补丁只裁定一次、正文/审阅/状态/目标/计划绑定冲突、预算耗尽、调用前取消、调用返回后失去 lease、传输失败重用已计数的 proposal、接受后崩溃、事件已写但最终 journal 未写的崩溃、真实 V1→V2 migration 后指导修复与下一次完整 load、旧 checkpoint 不能盖掉未检查的新正文、指导后真实检查链重跑、旧声明疑点保留并在新正文下重评、独立普通数学错误不能被指导绕过、提案 SHA 损坏，以及原状态快照写完但 dependency 未注册时的中断恢复和更新指针后仍可核验的原字节 SHA。

保留的失败与修正：

- `20260922T145048-576500`：15 PASS/1 FAIL。测试错误地要求没有结构化核算的定义正文返回 math PASS；程序正确保留 NEEDS_REVIEW。测试改为核对 check_math 实际再次执行且保留限制，没有改程序放宽数学检查。
- `20260922T145230-203400`：19 PASS；这是全局目录修正前的历史候选结果，不能替代当前 146 项。
- `20260922T145805-678200`：123 PASS/22 FAIL。测试副本的 basetemp 路径过长：迁移 evidence.json 路径 257 字符，原守卫使用的临时文件达 261 字符，Windows 写入失败。失败同时影响既有迁移用例。仅将隔离测试工作目录缩短到 workspace/gt*，相同候选完整重跑 145 PASS。该轮实际 Windows compile 用例已通过，早期 runner 的统一 NOT_RUN 字段不正确，旁注 correction JSON 保留更正而不覆盖旧记录。
- 初次普通 sandbox 下生成测试副本出现 PermissionError；另一次升级执行因自动审批额度服务失败而未执行。额度恢复后运行原命令。两者均不计入测试结果，未绕过审批。

生产合并时使用 `repair-guidance-pipeline-edits.json` 的四处精确替换，避免覆盖另一子任务的 Pipeline 修改；候选整体 SHA 和基线 SHA 在 `repair-guidance-helper-manifest.json`。本说明只证明候选工作流，不声称第二、三章真实制作已经通过。
